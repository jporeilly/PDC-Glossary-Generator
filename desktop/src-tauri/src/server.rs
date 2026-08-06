// Lifecycle of the bundled Python backend.
//
// The app is a FastAPI server plus a React SPA, so the desktop build has to run
// a real HTTP server and point a webview at it. Three things make that safe
// enough to hand to a workshop attendee:
//
//   1. A FREE PORT, chosen at launch. 5000 is a popular port and a second
//      instance (or anything else on the machine) must not turn into "the app
//      won't start".
//   2. A JOB OBJECT on Windows, so the server dies when we do - INCLUDING when
//      we are killed from Task Manager or crash. A leaked uvicorn keeps its
//      port and its lock on the state files, and the next launch then fails for
//      a reason the user cannot see.
//   3. STATE OUTSIDE THE INSTALL. GLOSSARY_STATE_DIR is set explicitly to the
//      per-user data directory rather than left to the app's own fallback, so
//      the packaged build never depends on probing Program Files.
use std::io::{self, BufRead, BufReader};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub struct Server {
    pub port: u16,
    child: Option<Child>,
}

/// The backend's last words.
///
/// Piping stdout/stderr without ever READING them is worse than not piping at
/// all: the traceback that explains the failure sits in a pipe nobody drains,
/// and a dead server looks identical to a slow one. Kept to the last few lines
/// because the useful part of a Python traceback is the end.
const LOG_LINES: usize = 40;
static SERVER_LOG: Mutex<Vec<String>> = Mutex::new(Vec::new());

fn record(line: String) {
    if let Ok(mut log) = SERVER_LOG.lock() {
        if log.len() >= LOG_LINES {
            log.remove(0);
        }
        log.push(line);
    }
}

/// Everything the backend has said, oldest first.
pub fn last_server_output() -> Vec<String> {
    SERVER_LOG.lock().map(|l| l.clone()).unwrap_or_default()
}

/// Drain a pipe on its own thread. Reading them inline would block startup.
fn drain<R: std::io::Read + Send + 'static>(stream: R, tag: &'static str) {
    thread::spawn(move || {
        for line in BufReader::new(stream).lines() {
            match line {
                Ok(l) => record(format!("[{tag}] {l}")),
                Err(_) => break,
            }
        }
    });
}

/// Does the backend answer a real HTTP request on this port?
///
/// Asked from RUST, not from the splash page. The page lives on a tauri://
/// origin, so a fetch() to http://127.0.0.1 is cross-origin: the request goes
/// out and the server logs a 200, but the webview refuses to hand the response
/// to JavaScript because FastAPI sends no Access-Control-Allow-Origin. The
/// promise rejects, the poll retries, and the splash spins forever against a
/// server that has been ready the whole time. Rust has no such rule.
pub fn http_ok(port: u16, path: &str) -> bool {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;

    let Ok(addr) = format!("127.0.0.1:{port}").parse() else { return false };
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_millis(400)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let req = format!(
        "GET {path} HTTP/1.1
Host: 127.0.0.1
Connection: close

"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = Vec::new();
    let _ = stream.read_to_end(&mut buf);
    let head = String::from_utf8_lossy(&buf[..buf.len().min(64)]);
    head.starts_with("HTTP/1.1 200") || head.starts_with("HTTP/1.0 200")
}

/// Is something listening there? Used to spot Ollama without shelling out.
///
/// A short timeout on purpose: this runs while the window is opening, and a
/// firewalled host that blackholes the SYN must not hold the splash up.
pub fn port_open(host: &str, port: u16) -> bool {
    use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
    use std::time::Duration;
    let Ok(mut addrs) = (host, port).to_socket_addrs() else {
        return false;
    };
    let Some(addr): Option<SocketAddr> = addrs.next() else {
        return false;
    };
    TcpStream::connect_timeout(&addr, Duration::from_millis(400)).is_ok()
}

/// Ask the OS for a free port by binding to :0, then release it.
///
/// There is an unavoidable race between releasing and uvicorn binding. It is
/// tiny and the alternative - letting uvicorn pick and parsing its stdout - is
/// worse, because it makes startup depend on log formatting we do not control.
fn free_port() -> io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// The vendored interpreter, or None to fall back to whatever `python` is on
/// PATH (which is how `tauri dev` runs against a plain checkout).
fn vendored_python(resource_dir: &Path) -> Option<PathBuf> {
    let exe = resource_dir.join("python").join("python.exe");
    if exe.is_file() {
        Some(exe)
    } else {
        None
    }
}

impl Server {
    /// Start the backend via `boot.py`, which owns api.py's app dir, storing
    /// state in `state_dir`.
    ///
    /// `python -m uvicorn api:app` does NOT work with the vendored runtime: the
    /// embeddable package's `._pth` replaces sys.path and drops the working
    /// directory, so api.py is unimportable however the process is launched.
    /// boot.py fixes the path explicitly and keeps packaged and dev launches on
    /// one code path.
    pub fn start(
        resource_dir: &Path,
        boot_py: &Path,
        app_dir: &Path,
        state_dir: &Path,
    ) -> io::Result<Self> {
        let port = free_port()?;

        let program = vendored_python(resource_dir).unwrap_or_else(|| PathBuf::from("python"));
        let args: Vec<String> = vec![
            boot_py.to_string_lossy().into_owned(),
            "--port".into(),
            port.to_string(),
            "--app-dir".into(),
            app_dir.to_string_lossy().into_owned(),
        ];

        let mut cmd = Command::new(&program);
        cmd.args(&args)
            .current_dir(app_dir)
            .env("GLOSSARY_STATE_DIR", state_dir)
            // uvicorn's default logging goes to stderr; capture both so a crash
            // is diagnosable instead of vanishing into a detached process.
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .stdin(Stdio::null());

        #[cfg(windows)]
        cmd.creation_flags(CREATE_NO_WINDOW);

        let mut child = cmd.spawn()?;

        // Start draining IMMEDIATELY. A Python traceback is a few hundred bytes,
        // which fits in the pipe buffer, but uvicorn's request logging does not -
        // an undrained pipe eventually blocks the server mid-run.
        if let Some(out) = child.stdout.take() {
            drain(out, "out");
        }
        if let Some(err) = child.stderr.take() {
            drain(err, "err");
        }

        #[cfg(windows)]
        job::assign_to_kill_on_close_job(&child)?;

        Ok(Server {
            port,
            child: Some(child),
        })
    }

    /// Has the backend exited? `Some(false)` while running, `Some(true)` once
    /// it has died, `None` if we cannot tell.
    ///
    /// This is what separates "dead" from "merely slow", and the splash needs
    /// that distinction: a cold start on a slow disk can take a long time, but a
    /// process that has EXITED is never going to answer, and waiting out a
    /// timeout before saying so wastes the user's time and invites a support
    /// email about a failure the app already knew about.
    pub fn exited(&mut self) -> Option<bool> {
        let child = self.child.as_mut()?;
        match child.try_wait() {
            Ok(Some(_)) => Some(true),
            Ok(None) => Some(false),
            Err(_) => None,
        }
    }

    pub fn url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }

    /// Best-effort shutdown. The job object is the real guarantee on Windows;
    /// this just makes the common case immediate and tidy.
    pub fn stop(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(windows)]
mod job {
    //! Kill-on-close job object.
    //!
    //! Without this, closing the app normally kills uvicorn (via `stop`), but a
    //! crash or a Task Manager kill leaves it running. It then holds the port
    //! and the state files, and the next launch fails silently. The job is
    //! created once and leaked deliberately: its handle must outlive every
    //! child, and the OS tears it down when this process ends - which is
    //! precisely the behaviour we want.
    use std::io;
    use std::process::Child;
    use std::sync::OnceLock;

    use windows::Win32::Foundation::{HANDLE, INVALID_HANDLE_VALUE};
    use windows::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
        JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows::Win32::System::Threading::{OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE};

    struct JobHandle(HANDLE);
    // The handle is only ever passed to AssignProcessToJobObject, which is
    // thread-safe; OnceLock requires Send + Sync.
    unsafe impl Send for JobHandle {}
    unsafe impl Sync for JobHandle {}

    static JOB: OnceLock<Option<JobHandle>> = OnceLock::new();

    fn job() -> Option<HANDLE> {
        JOB.get_or_init(|| unsafe {
            let handle = CreateJobObjectW(None, None).ok()?;
            if handle == INVALID_HANDLE_VALUE || handle.is_invalid() {
                return None;
            }
            let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const core::ffi::c_void,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if ok.is_err() {
                return None;
            }
            Some(JobHandle(handle))
        })
        .as_ref()
        .map(|h| h.0)
    }

    pub fn assign_to_kill_on_close_job(child: &Child) -> io::Result<()> {
        // A failure here is not fatal: the app still works, it just loses the
        // crash-safety net. Better a running app than a refusal to start.
        let Some(job) = job() else { return Ok(()) };
        unsafe {
            let Ok(proc) = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, false, child.id())
            else {
                return Ok(());
            };
            let _ = AssignProcessToJobObject(job, proc);
        }
        Ok(())
    }
}

/// Minimal HTTP over a plain socket, for talking to Ollama on localhost.
///
/// No HTTP crate on purpose. The only endpoint this shell ever calls is
/// 127.0.0.1:11434 - plain text, no TLS, no redirects, no auth - and pulling in
/// a full client (and its TLS stack) to POST one JSON body would add more to the
/// binary and the build than the feature is worth.
pub mod ollama {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;

    fn request(method: &str, path: &str, body: Option<&str>, read_secs: u64) -> Option<String> {
        let mut stream = TcpStream::connect_timeout(
            &"127.0.0.1:11434".parse().ok()?,
            Duration::from_millis(500),
        )
        .ok()?;
        // A model that stalls must not hold the panel open forever; the caller
        // has a support address to fall back on.
        stream.set_read_timeout(Some(Duration::from_secs(read_secs))).ok()?;
        stream.set_write_timeout(Some(Duration::from_secs(5))).ok()?;

        let payload = body.unwrap_or("");
        let req = format!(
            "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:11434\r\nConnection: close\r\n\
             Content-Type: application/json\r\nContent-Length: {}\r\n\r\n{payload}",
            payload.len()
        );
        stream.write_all(req.as_bytes()).ok()?;

        let mut raw = Vec::new();
        // read_to_end returns Err on timeout, but whatever arrived before that is
        // still in the buffer and may well be a complete response.
        let _ = stream.read_to_end(&mut raw);
        let text = String::from_utf8_lossy(&raw).into_owned();
        let idx = text.find("\r\n\r\n")?;
        Some(text[idx + 4..].to_string())
    }

    /// First installed model, or None when Ollama is up but empty - which is a
    /// distinct state worth reporting, not a failure to connect.
    pub fn first_model() -> Option<String> {
        let body = request("GET", "/api/tags", None, 5)?;
        let v: serde_json::Value = serde_json::from_str(&body).ok()?;
        v.get("models")?
            .as_array()?
            .first()?
            .get("name")?
            .as_str()
            .map(String::from)
    }

    /// Ask the local model what to try. Returns its text, or None.
    pub fn suggest(model: &str, prompt: &str) -> Option<String> {
        let payload = serde_json::json!({
            "model": model,
            "prompt": prompt,
            "stream": false,
            // Short and cool: this is troubleshooting, not prose, and a long
            // rambling answer is worse than none when someone is stuck.
            "options": { "temperature": 0.2, "num_predict": 400 }
        })
        .to_string();
        let body = request("POST", "/api/generate", Some(&payload), 120)?;
        let v: serde_json::Value = serde_json::from_str(&body).ok()?;
        v.get("response")?.as_str().map(|s| s.trim().to_string())
    }
}
