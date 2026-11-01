TURBALL UPDATE STATUS — 4.5.2 CAPTURE / DIAGNOSTICS UPDATE

The supplied website is release 98f9b3003e60-41220884867-1. Its lobby
chunk-DLWGG6LS.js imports gameplay from chunk-KALAXRXF.js. The supplied
HAR contains the lobby but no request/response for that gameplay module.
Direct retrieval of turball.io is blocked in the development environment.
The gameplay patch therefore remains UNVERIFIED for this new release.
This update does not claim to make the new game's AI/TAS adapter compatible.

To obtain the one missing file without exporting another HAR:
1. Update files INSIDE your existing unpacked extension folder. Keep its
   directory/extension ID, imported models and existing private .bin files.
2. Reload the extension at chrome://extensions; close DevTools on the game tab.
3. Open Turball, click Enable + reload in the extension popup, then Free Play.
4. Reopen the extension popup. Click Save gameplay JS and upload that .js file.
   The expected current filename is chunk-KALAXRXF.js; future releases may
   change it. Save diagnostics is an optional, smaller connection report.
5. A grey Save gameplay JS button means the gameplay module has not yet been
   captured. Enter Free Play after enabling/reloading, then reopen the popup.

An unsupported module is passed through unchanged so the game can still load.
Captures remain in this browser session until a new scan or tab close; they
survive a background worker restart. Nothing is uploaded automatically.
Connection reports contain public asset paths/hashes/status, not HAR headers,
cookies, account data or the full game source. Exports require a popup click.
No new extension permissions are requested. Existing Car Soccer features and
model storage are retained. The source-only ZIP does not include game assets,
uploaded HTML/HAR files or private model binaries.

The previous validated minified Turball anchors target gameplay chunk-IORKFJL5.js
(release 6ecc13b81511-38608307515-1). They are deliberately not guessed from
the new lobby. The full gameplay module is needed for a tested adapter rewrite.
