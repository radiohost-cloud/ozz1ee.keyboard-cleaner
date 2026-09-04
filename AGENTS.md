# Extension development instructions

- Read the active Omalaunch `EXTENSIONS.md` contract before you change this plugin.
- This plugin ID is `ozz1ee.keyboard-cleaner`. Keep it consistent in `manifest.json` and `omalaunch.json`.
- Omarchy watches this plugin directory. Use atomic file replacement when possible and do not create temporary files inside it.
- Validate the plugin with `omarchy plugin validate .` after changes.
- Finish each implementation turn by enabling the plugin with `omarchy plugin enable ozz1ee.keyboard-cleaner` so the user can review it.
- Do not store secrets, local state, caches, or machine-specific paths in the plugin.
- Add clear installation and usage instructions to `README.md` before publication.
- When the extension is ready, ask whether the user wants to publish it for other people. Keep it local if they do not.
- Do not create a remote repository, publish a release, or submit to the Omalaunch Extension Directory without explicit user approval.
- If the user wants to share the extension, offer the Omalaunch Extension Directory as one publishing option and ask before preparing a submission: https://github.com/DanielLemky/omalaunch-extensions.
