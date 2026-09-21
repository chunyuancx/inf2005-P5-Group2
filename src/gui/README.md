# Glass desktop

Run `python -m src` from the repository root. The default GUI opens in an Edge
or Chrome app window. It uses local HTML/CSS for backdrop blur and a fixed,
responsive card layout, with the existing Python workflows and native file dialogs.
No Flask server, hosted service, frontend build step, or new package is needed.

Media preview spans the first row. Source, Protection and Verification share the
second row on desktop, reflowing into two columns or a single column on smaller
screens. Preview stays above the steps.

The card order is fixed; resizing the window reflows the layout without changing
selected media or active operations.

The renderer binds only to a random loopback port and uses a random session
path. Closing the app lets any active operation finish before shutdown;
refreshing reconnects to the current session. The interface does not replace or
implement the pending media service adapters.

`python -m src --native` opens the earlier Tk view. `--no-open` starts the glass
renderer and prints its local URL without opening a window.

On this workstation, the working Tk interpreter is MSYS2 Python. In PowerShell:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' -m src
```

The application entry point still uses `UnconfiguredService` adapters, as it did
before the visual redesign. Connect the team's service implementations through
`ApplicationController` to enable real media processing.

## GUI regression checks

Run the full suite with `python -m pytest tests -q`. This includes both the
unittest-style GUI tests and pytest-style controller/engine tests; unittest
discovery alone does not execute the latter.

The repeatable browser suite launches an isolated headless Edge profile and a
separate test backend. It clicks the rendered controls, exercises protect/save/
verify and errors, checks the Test studio's JSON/log evidence, refreshes the
session, checks six window widths, and closes the app.

```powershell
python -m tests.gui_browser --tk-python 'C:\msys64\ucrt64\bin\python.exe'
```

On other workstations, omit `--tk-python` if the current Python has working Tk,
and pass `--browser <path>` for a different Edge/Chrome location. The driver uses
`websocket-client` (optional test requirements: `tests/requirements-gui.txt`).
Screenshots, reports and a check summary are saved in `test-evidence/gui-*`.

Browser tests use the real GUI, controller and reporting runner with controlled
media service doubles. Native dialog selections are stubbed so the tests need
no manual file picking. These checks do not validate the pending production
media adapters or the operating system's dialog rendering.
