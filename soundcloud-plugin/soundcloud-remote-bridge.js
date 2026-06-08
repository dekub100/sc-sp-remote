/**
 * @name soundcloud-remote-bridge
 * @description Bridges soundcloud-rpc to the sc-spotify-remote Python server via WebSocket
 * @version 2.0.0
 * @license MIT
 *
 * v2.0.0 — Full rewrite.
 * FIXED: Volume control now uses the correct hover-expand-click sequence.
 *        Setting audio.volume directly does NOT work — SoundCloud overrides it.
 * FIXED: Play state uses navigator.mediaSession.playbackState (reliable).
 * FIXED: Metadata uses navigator.mediaSession primary, DOM fallback.
 * FIXED: Seek DOM fallback uses actual duration, not a hardcoded 300000.
 * FIXED: Volume read-back uses slider height ratio, not audio.volume.
 */

module.exports = {
  onEnable() {},
  onDisable() {},
  onTrackChange(track) {},

  contentScript() {
    return `
            (function() {
                if (window.__scRemoteLoaded) return;
                window.__scRemoteLoaded = true;

                var VERSION = '2.0.0';
                var SERVER_PORT = 8889;
                var SERVER_URL = 'ws://localhost:' + SERVER_PORT + '/?client=soundcloud&protocolVersion=1';
                var ws = null;
                var reconnectDelay = 1000;
                var MAX_RECONNECT = 10000;
                var pollInterval = null;
                var lastTrackId = '';

                /* ─── Media element tracking ───────────────────────────────────── */

                var _trackedMedia = [];

                function _scanMediaElements(root) {
                    root = root || document;
                    var els = root.querySelectorAll ? root.querySelectorAll('audio') : [];
                    for (var i = 0; i < els.length; i++) {
                        if (_trackedMedia.indexOf(els[i]) === -1) _trackedMedia.push(els[i]);
                    }
                    var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
                    for (var i = 0; i < all.length; i++) {
                        if (all[i].shadowRoot) _scanMediaElements(all[i].shadowRoot);
                    }
                }

                // Hook createElement so we catch audio elements before they attach to the DOM
                var _origCreateElement = document.createElement.bind(document);
                document.createElement = function(tagName, options) {
                    var el = _origCreateElement(tagName, options);
                    if ((tagName || '').toLowerCase() === 'audio' && _trackedMedia.indexOf(el) === -1) {
                        _trackedMedia.push(el);
                    }
                    return el;
                };

                // Hook .play() so we catch elements created any other way
                var _origPlay = HTMLMediaElement.prototype.play;
                HTMLMediaElement.prototype.play = function() {
                    if (_trackedMedia.indexOf(this) === -1) _trackedMedia.push(this);
                    return _origPlay.apply(this, arguments);
                };

                // MutationObserver for elements added after page load
                (function() {
                    var mo = new MutationObserver(function(muts) {
                        for (var m = 0; m < muts.length; m++) {
                            var nodes = muts[m].addedNodes;
                            for (var n = 0; n < nodes.length; n++) {
                                var node = nodes[n];
                                if (node.nodeType !== 1) continue;
                                if (node.tagName === 'AUDIO' && _trackedMedia.indexOf(node) === -1) {
                                    _trackedMedia.push(node);
                                }
                                if (node.querySelectorAll) {
                                    var kids = node.querySelectorAll('audio');
                                    for (var k = 0; k < kids.length; k++) {
                                        if (_trackedMedia.indexOf(kids[k]) === -1) _trackedMedia.push(kids[k]);
                                    }
                                }
                                if (node.shadowRoot) _scanMediaElements(node.shadowRoot);
                            }
                        }
                    });
                    if (document.body) {
                        mo.observe(document.body, { childList: true, subtree: true });
                    } else {
                        document.addEventListener('DOMContentLoaded', function() {
                            mo.observe(document.body, { childList: true, subtree: true });
                        });
                    }
                })();

                _scanMediaElements();

                function _bestMedia() {
                    // Prefer an element that's actively playing
                    for (var i = 0; i < _trackedMedia.length; i++) {
                        var m = _trackedMedia[i];
                        if (!m.paused && m.duration > 0) return m;
                    }
                    // Then any element with valid duration
                    for (var i = 0; i < _trackedMedia.length; i++) {
                        if (_trackedMedia[i].duration > 0) return _trackedMedia[i];
                    }
                    return _trackedMedia.length > 0 ? _trackedMedia[0] : null;
                }

                /* ─── Logging ──────────────────────────────────────────────────── */

                function log(level, msg) {
                    var full = '[sc-remote v' + VERSION + '] ' + msg;
                    if (level === 'error') console.error(full);
                    else if (level === 'warning') console.warn(full);
                    if (ws && ws.readyState === 1) {
                        try { ws.send(JSON.stringify({ type: 'clientLog', level: level, message: msg })); } catch(e) {}
                    }
                }

                /* ─── State helpers ────────────────────────────────────────────── */

                function _getCover() {
                    // navigator.mediaSession is the most reliable source
                    var ms = navigator.mediaSession;
                    if (ms && ms.metadata && ms.metadata.artwork && ms.metadata.artwork.length > 0) {
                        var art = ms.metadata.artwork;
                        var best = art[0];
                        var bestSize = 0;
                        for (var i = 0; i < art.length; i++) {
                            var sz = parseInt((art[i].sizes || '').split('x')[0]) || 0;
                            if (sz > bestSize) { bestSize = sz; best = art[i]; }
                        }
                        if (best.src) return best.src;
                    }
                    // DOM fallback: background-image on the badge artwork span
                    var span = document.querySelector('.playbackSoundBadge__avatar .image__lightOutline span');
                    if (span) {
                        var bg = (span.style.backgroundImage || '').replace(/^url\\(['"]?|['"]?\\)$/g, '');
                        if (bg) return bg.replace(/-t\\d+x\\d+/, '-t500x500');
                    }
                    return '';
                }

                function _getVolume() {
                    // Read the slider height ratio — reflects what SoundCloud's UI shows.
                    // NOTE: When the slider is collapsed (not hovered), getBoundingClientRect()
                    // may still return its real layout dimensions since SC hides via opacity/transform.
                    // If it returns 0 we fall back to the audio element.
                    var progress = document.querySelector('.volume__sliderProgress');
                    var bg = document.querySelector('.volume__sliderBackground');
                    if (progress && bg) {
                        var ph = progress.getBoundingClientRect().height;
                        var bh = bg.getBoundingClientRect().height;
                        if (bh > 0) return ph / bh;  // 0.0 – 1.0
                    }
                    var m = _bestMedia();
                    return m ? m.volume : 1;
                }

                function getState() {
                    var ms = navigator.mediaSession;

                    // Play state — mediaSession is the authority
                    var isPlaying = ms ? ms.playbackState === 'playing' : false;

                    // Metadata — mediaSession first, DOM fallback
                    var title = (ms && ms.metadata && ms.metadata.title) || '';
                    var artist = (ms && ms.metadata && ms.metadata.artist) || '';

                    if (!title) {
                        var titleEl = document.querySelector('.playbackSoundBadge__title a');
                        title = titleEl ? (titleEl.getAttribute('title') || titleEl.textContent.trim()) : '';
                    }
                    if (!artist) {
                        var artistEl = document.querySelector('.playbackSoundBadge__lightLink');
                        artist = artistEl ? artistEl.textContent.trim() : '';
                    }

                    var urlEl = document.querySelector('.playbackSoundBadge__titleLink');
                    var trackUrl = urlEl ? urlEl.href.split('?')[0] : '';

                    var m = _bestMedia();
                    var progressMs = m ? Math.floor(m.currentTime * 1000) : 0;
                    var durationMs = m ? Math.floor((isFinite(m.duration) ? m.duration : 0) * 1000) : 0;

                    return {
                        type: 'scStateUpdate',
                        track: title,
                        artist: artist,
                        coverUrl: _getCover(),
                        id: trackUrl,
                        isPlaying: isPlaying,
                        progressMs: progressMs,
                        durationMs: durationMs,
                        volume: _getVolume()
                    };
                }

                /* ─── Controls ─────────────────────────────────────────────────── */

                function scSeek(positionMs) {
                    if (isNaN(positionMs) || positionMs < 0) return;
                    var m = _bestMedia();

                    // Direct currentTime works on SoundCloud (unlike volume)
                    if (m && m.duration > 0 && isFinite(m.duration)) {
                        m.currentTime = Math.min(positionMs / 1000, m.duration);
                        return;
                    }

                    // DOM fallback: mouse events on the progress bar
                    var el = document.querySelector('.playbackTimeline__progressWrapper');
                    if (!el) return;

                    // Get duration from DOM if the audio element doesn't have it yet
                    var durationMs = (m && isFinite(m.duration)) ? m.duration * 1000 : 0;
                    if (!durationMs) {
                        // .playbackTimeline__duration > span[1] holds the total time text
                        var spans = document.querySelectorAll('.playbackTimeline__duration > span');
                        var durText = spans[1] ? (spans[1].innerText || '') : '';
                        var parts = durText.split(':').map(Number);
                        if (parts.length === 2) durationMs = (parts[0] * 60 + parts[1]) * 1000;
                        else if (parts.length === 3) durationMs = (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000;
                    }
                    if (!durationMs) return;

                    var ratio = Math.max(0, Math.min(1, positionMs / durationMs));
                    var r = el.getBoundingClientRect();
                    if (r.width <= 0) return;

                    var opts = {
                        view: window, bubbles: true, cancelable: true,
                        clientX: r.left + r.width * ratio,
                        clientY: r.top + r.height / 2
                    };
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                }

                function scSetVolume(volume) {
                    // volume is 0.0 – 1.0
                    volume = Math.max(0, Math.min(1, volume));

                    // ── WHY NOT audio.volume ──────────────────────────────────────────
                    // Setting m.volume directly does NOT work. SoundCloud's player
                    // manages volume internally and overwrites audio.volume from its own
                    // state. The only reliable method is simulating the mouse interaction
                    // on the volume slider itself.
                    // ─────────────────────────────────────────────────────────────────

                    var volContainer = document.querySelector('.volume');
                    if (!volContainer) {
                        log('warning', 'scSetVolume: .volume container not found');
                        return;
                    }

                    // Step 1: Dispatch mouseover + mousemove to trigger SoundCloud's
                    //         hover handler. This adds 'expanded' and 'hover' classes.
                    var hoverOpts = { view: window, bubbles: true, cancelable: true, clientX: 0, clientY: 0 };
                    volContainer.dispatchEvent(new MouseEvent('mouseover', hoverOpts));
                    volContainer.dispatchEvent(new MouseEvent('mousemove', hoverOpts));

                    // Step 2: Poll until .volume.expanded.hover exists.
                    //         SoundCloud adds these classes asynchronously after the
                    //         mouseover. 20 attempts × 25ms = 500ms maximum wait.
                    var attempts = 0;
                    var poll = setInterval(function() {
                        attempts++;

                        var expanded = document.querySelector('.volume.expanded.hover');
                        if (expanded) {
                            clearInterval(poll);

                            var bg = document.querySelector('.volume__sliderBackground');
                            if (!bg) {
                                log('warning', 'scSetVolume: slider background not found after expand');
                                return;
                            }

                            var loc = bg.getBoundingClientRect();
                            if (loc.height <= 0) {
                                log('warning', 'scSetVolume: slider has zero height');
                                return;
                            }

                            // Step 3: Calculate Y position.
                            //   The slider is vertical: bottom = max volume, top = 0.
                            //   clientY = loc.bottom - (volume * loc.height) + 5
                            //   The +5 offset is empirically required (matches WebNowPlaying).
                            var targetY = loc.bottom - (volume * loc.height) + 5;
                            var clickOpts = {
                                view: window, bubbles: true, cancelable: true,
                                clientX: loc.left + loc.width / 2,
                                clientY: targetY
                            };

                            // Step 4: Simulate the click on the slider track.
                            bg.dispatchEvent(new MouseEvent('mousedown', clickOpts));
                            bg.dispatchEvent(new MouseEvent('mouseup', clickOpts));

                            // Step 5: Mouse out to dismiss the slider.
                            volContainer.dispatchEvent(new MouseEvent('mouseout', hoverOpts));

                        } else if (attempts >= 20) {
                            clearInterval(poll);
                            log('warning', 'scSetVolume: slider never expanded (volume unavailable while SC is idle?)');
                        }
                    }, 25);
                }

                /* ─── Command dispatcher ───────────────────────────────────────── */

                function executeCommand(cmd) {
                    switch (cmd.command) {
                        case 'togglePlay':
                        case 'play':
                        case 'pause': {
                            // .playControl is the current selector (soundcloud-rpc also uses this)
                            var btn = document.querySelector('.playControl');
                            if (btn) { btn.click(); break; }
                            // Audio element fallback
                            var m = _bestMedia();
                            if (m) { m.paused ? m.play() : m.pause(); }
                            break;
                        }
                        case 'next': {
                            var el = document.querySelector('.skipControl__next');
                            if (el) el.click();
                            break;
                        }
                        case 'previous': {
                            var el = document.querySelector('.skipControl__previous');
                            if (el) el.click();
                            break;
                        }
                        case 'seek': {
                            var ms = cmd.position_ms !== undefined ? cmd.position_ms : cmd.position;
                            if (ms !== undefined) scSeek(Number(ms));
                            break;
                        }
                        case 'seekForward': {
                            if (cmd.offset !== undefined) {
                                var m = _bestMedia();
                                if (m && isFinite(m.duration) && m.duration > 0) {
                                    var currentMs = Math.floor(m.currentTime * 1000);
                                    scSeek(currentMs + Number(cmd.offset));
                                }
                            }
                            break;
                        }
                        case 'seekBack': {
                            if (cmd.offset !== undefined) {
                                var m = _bestMedia();
                                if (m && isFinite(m.duration) && m.duration > 0) {
                                    var currentMs = Math.floor(m.currentTime * 1000);
                                    scSeek(Math.max(currentMs - Number(cmd.offset), 0));
                                }
                            }
                            break;
                        }
                        case 'setVolume': {
                            if (cmd.volume !== undefined) scSetVolume(Number(cmd.volume));
                            break;
                        }
                        case 'like': {
                            var btn = document.querySelector('.playbackSoundBadge button.sc-button-like')
                                   || document.querySelector('.playControls__soundBadge button.sc-button-like');
                            if (btn) btn.click();
                            break;
                        }
                    }
                }

                /* ─── WebSocket ────────────────────────────────────────────────── */

                function connect() {
                    try {
                        ws = new WebSocket(SERVER_URL);
                    } catch (e) {
                        log('error', 'WebSocket creation failed: ' + e.message);
                        scheduleReconnect();
                        return;
                    }

                    ws.onopen = function() {
                        reconnectDelay = 1000;
                        ws.send(JSON.stringify({ type: 'register', client: 'soundcloud' }));
                        var state = getState();
                        ws.send(JSON.stringify(state));
                        lastTrackId = state.id;
                        startPolling();
                    };

                    ws.onmessage = function(e) {
                        try {
                            var msg = JSON.parse(e.data);
                            if (msg.type === 'scPlaybackControl') {
                                executeCommand(msg);
                                // Send updated state after a short delay so SC has time to react
                                setTimeout(function() {
                                    if (ws && ws.readyState === 1) ws.send(JSON.stringify(getState()));
                                }, 400);
                            } else if (msg.type === 'scVolumeUpdate') {
                                if (msg.volume !== undefined) scSetVolume(Number(msg.volume));
                            } else if (msg.type === 'config' && msg.pollingIntervalMs) {
                                startPolling(msg.pollingIntervalMs);
                            }
                        } catch (err) {
                            log('error', 'Message parse error: ' + err.message);
                        }
                    };

                    ws.onclose = function() {
                        stopPolling();
                        scheduleReconnect();
                    };

                    ws.onerror = function() {};
                }

                function scheduleReconnect() {
                    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT);
                    setTimeout(connect, reconnectDelay);
                }

                function startPolling(intervalMs) {
                    stopPolling();
                    pollInterval = setInterval(function() {
                        if (!ws || ws.readyState !== 1) return;
                        var state = getState();
                        if (state.id && state.id !== lastTrackId) lastTrackId = state.id;
                        ws.send(JSON.stringify(state));
                    }, intervalMs || 500);
                }

                function stopPolling() {
                    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
                }

                /* ─── Init ─────────────────────────────────────────────────────── */

                connect();

                window.__scrpc_cleanup_soundcloud_remote_bridge = function() {
                    stopPolling();
                    if (ws) { ws.close(); ws = null; }
                    delete window.__scRemoteLoaded;
                };
            })();
        `;
  },
};
