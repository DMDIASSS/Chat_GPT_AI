TURBALL 332c59c495f7-38732477493-1 (detected from uploaded HTML/HAR)

This release was created because the extension targeted a previous single
chunk-IORKFJL5.js gameplay asset. The Turball homepage's current JavaScript
imports ./chunk-TVJT3ATP.js when starting gameplay.

Version 4.3.1 now scans /assets/app/chunk-*.js for a real startGame export
and only attempts to patch that file; all other chunks are passed through.

IMPORTANT: The user's newest HAR does NOT include the actual
chunk-TVJT3ATP.js gameplay JavaScript; only the reference to the chunk is
present. We cannot confirm that the old AI patch's minified anchors are still
valid. A popup showing 'unsupported' means the game was deliberately left
unchanged to avoid a broken/crashing game.

TO PROVIDE THE MISSING FILE FOR A FULL COMPATIBILITY UPDATE
1. Temporarily DISABLE the trainer extension on the Turball tab.
2. On https://turball.io press F12 > Network. Tick Disable cache.
3. Reload. Enter Free Play or a match (not just the home screen).
4. Filter Network by TVJT3ATP or `chunk-` and select the gameplay module.
   The relevant filename can change again after a new release. Look for
   'chunk-TVJT3ATP.js' in version 332c59c495f7-38732477493-1.
5. In the Network response/details, copy or save the JS response as a file,
   or export HAR WITH CONTENT after gameplay has started.
6. Send the gameplay JS so the patch anchors can be updated and validated.

Do not confuse the homepage entry `game-ATG57U4Q.js` with the dynamic
`chunk-TVJT3ATP.js` gameplay module. The entry alone is insufficient.

Version 4.3.2 adds an experimental F9 rendering-only ball visibility workaround. This does not change the compatibility status of unknown Turball game builds.
