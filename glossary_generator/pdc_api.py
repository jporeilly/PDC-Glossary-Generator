"""
pdc_api.py — compatibility shim over the shared `pdc_client` package.

The PDC Public API client used to live here as the `pdc_api` package; it was
extracted to <repo-root>/pdc_client so other apps (e.g. the Policy Generator)
can share one client. Everything the app and tests ever imported from
`pdc_api` — including the underscore helpers — is re-exported here, so
`import pdc_api` keeps working unchanged.
"""
import os as _os
import sys as _sys

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

import pdc_client as _pdc_client

# Re-export the entire public+private surface (the old package __init__ already
# re-exported underscore helpers like _under_root on purpose).
for _n in dir(_pdc_client):
    if not _n.startswith("__"):
        globals()[_n] = getattr(_pdc_client, _n)

__doc__ = (__doc__ or "") + "\n\n" + (_pdc_client.__doc__ or "")
