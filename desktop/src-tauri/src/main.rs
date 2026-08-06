// PDC Glossary Generator - desktop shell.
//
// The app itself is unchanged: a FastAPI server serving the React SPA. This
// binary only starts that server on a free port, waits for it to answer, and
// points a webview at it. Everything the user sees is still the web UI, so the
// browser and desktop builds cannot drift apart.
//
// Paths are resolved through Tauri's path helpers, never hardcoded - the
// install root is not predictable and the app directory is read-only.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod server;

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use tauri::{Manager, State};

use server::Server;

/// Shared so the window-close handler can stop the server without borrowing
/// from the window - going through `State` there ties the borrow to a
/// temporary, which does not outlive the closure.
type SharedServer = Arc<Mutex<Option<Server>>>;

struct AppState {
    server: SharedServer,
}

/// Where api.py lives.
///
/// Packaged: bundle.resources drops the app tree next to the executable.
/// Dev (`npm run tauri:dev`): walk up to the checkout and use it in place, so
/// there is no build step between editing Python and seeing the change.
fn app_dir(handle: &tauri::AppHandle) -> PathBuf {
    // The staged tree mirrors the repo (app/glossary_generator + app/frontend),
    // because api.py resolves the built UI as ../frontend/dist relative to
    // itself. Flattening it would leave the server up with nothing to serve.
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = res.join("app").join("glossary_generator");
        if packaged.join("api.py").is_file() {
            return packaged;
        }
    }
    let checkout = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("glossary_generator");
    checkout
}

/// boot.py - staged beside the app tree, or taken from the checkout in dev.
/// Mirrors app_dir()'s packaged-then-checkout resolution deliberately: one rule,
/// applied twice, beats two rules that can disagree about which tree is live.
fn boot_py(handle: &tauri::AppHandle) -> PathBuf {
    if let Ok(res) = handle.path().resource_dir() {
        let packaged = res.join("app").join("boot.py");
        if packaged.is_file() {
            return packaged;
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("boot.py")
}

/// Per-user state directory. Passed to the server explicitly rather than left
/// to its own fallback, so the packaged build never has to probe Program Files.
fn state_dir(handle: &tauri::AppHandle) -> PathBuf {
    handle
        .path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// The splash page polls this until the server answers, then navigates to it.
#[tauri::command]
fn server_url(state: State<'_, AppState>) -> Option<String> {
    state.server.lock().ok()?.as_ref().map(|s| s.url())
}

/// Surfaced on the splash when startup fails, so a dead backend reads as an
/// error message rather than a permanently blank window.
#[tauri::command]
fn diagnostics(handle: tauri::AppHandle) -> serde_json::Value {
    let dir = app_dir(&handle);
    serde_json::json!({
        "app_dir": dir.to_string_lossy(),
        "api_py_found": dir.join("api.py").is_file(),
        "boot_py": boot_py(&handle).to_string_lossy(),
        "boot_py_found": boot_py(&handle).is_file(),
        "state_dir": state_dir(&handle).to_string_lossy(),
        "vendored_python": handle
            .path()
            .resource_dir()
            .map(|r| r.join("python").join("python.exe").is_file())
            .unwrap_or(false),
    })
}

fn main() {
    let shared: SharedServer = Arc::new(Mutex::new(None));
    let for_close = shared.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(AppState {
            server: shared.clone(),
        })
        .invoke_handler(tauri::generate_handler![server_url, diagnostics])
        .setup(move |app| {
            let handle = app.handle().clone();
            let resource_dir = handle.path().resource_dir().unwrap_or_default();
            let app_dir = app_dir(&handle);
            let boot_py = boot_py(&handle);
            let state_dir = state_dir(&handle);
            std::fs::create_dir_all(&state_dir).ok();

            match Server::start(&resource_dir, &boot_py, &app_dir, &state_dir) {
                Ok(srv) => {
                    *shared.lock().unwrap() = Some(srv);
                }
                Err(e) => {
                    // Do not abort: the splash reports this, with the
                    // diagnostics above, which is far more useful than a window
                    // that never appears.
                    eprintln!("failed to start the backend: {e}");
                }
            }
            Ok(())
        })
        .on_window_event(move |_window, event| {
            // Stop the server on close rather than waiting for process exit, so
            // the port is free immediately if the user relaunches.
            if let tauri::WindowEvent::Destroyed = event {
                if let Ok(mut guard) = for_close.lock() {
                    if let Some(srv) = guard.as_mut() {
                        srv.stop();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running the PDC Glossary Generator shell");
}
