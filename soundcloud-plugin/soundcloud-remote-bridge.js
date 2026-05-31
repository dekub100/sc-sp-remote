/**
 * @name soundcloud-remote-bridge
 * @description Bridges soundcloud-rpc to the sc-spotify-remote Python server via WebSocket
 * @version 1.0.3
 * @license MIT
 *
 * v1.0.3 — Track audio element via prototype hooks + MutationObserver + shadow DOM.
 * Seek/volume via media element when found, DOM simulation fallback.
 * Selectors based on soundcloud-rpc's audioMonitorService.ts
 */

module.exports = {
    onEnable() {
    },

    onDisable() {
    },

    onTrackChange(track) {
        // Track changes are also handled by the content script via DOM polling.
    },

    contentScript() {
        return `
            (function() {
                if (window.__scRemoteLoaded) return;
                window.__scRemoteLoaded = true;

                var VERSION = '1.0.3';
                var SERVER_PORT = 8889;
                var SERVER_URL = 'ws://localhost:' + SERVER_PORT + '/?client=soundcloud&protocolVersion=1';
                var ws = null;
                var reconnectDelay = 1000;
                var MAX_RECONNECT = 10000;
                var pollInterval = null;
                var lastTrackUrl = '';

                /* --- Track audio element via prototype hooks --- */
                var _trackedMedia = [];

                function _scanMediaElements(root) {
                    if (!root) root = document;
                    var els = (root.querySelectorAll || function(s){return [];}).call(root, 'audio, video');
                    for (var i = 0; i < els.length; i++) {
                        if (_trackedMedia.indexOf(els[i]) === -1) _trackedMedia.push(els[i]);
                    }
                    var all = (root.querySelectorAll || function(s){return [];}).call(root, '*');
                    for (var i = 0; i < all.length; i++) {
                        if (all[i].shadowRoot) _scanMediaElements(all[i].shadowRoot);
                    }
                }

                var _origCreateElement = document.createElement.bind(document);
                document.createElement = function(tagName, options) {
                    var el = _origCreateElement(tagName, options);
                    var tag = (tagName || '').toLowerCase();
                    if (tag === 'audio' || tag === 'video') {
                        if (_trackedMedia.indexOf(el) === -1) _trackedMedia.push(el);
                    }
                    return el;
                };

                var _origAudio = window.Audio;
                window.Audio = function(src) {
                    var el = new _origAudio(src);
                    if (_trackedMedia.indexOf(el) === -1) _trackedMedia.push(el);
                    return el;
                };

                var _origPlay = HTMLMediaElement.prototype.play;
                HTMLMediaElement.prototype.play = function() {
                    if (_trackedMedia.indexOf(this) === -1) _trackedMedia.push(this);
                    return _origPlay.apply(this, arguments);
                };

                (function _setupMediaObserver() {
                    var mo = new MutationObserver(function(muts) {
                        for (var m = 0; m < muts.length; m++) {
                            var nodes = muts[m].addedNodes;
                            for (var n = 0; n < nodes.length; n++) {
                                var node = nodes[n];
                                if (node.nodeType === 1) {
                                    if (node.matches && node.matches('audio, video')) {
                                        if (_trackedMedia.indexOf(node) === -1) _trackedMedia.push(node);
                                    }
                                    if (node.querySelectorAll) {
                                        var kids = node.querySelectorAll('audio, video');
                                        for (var k = 0; k < kids.length; k++) {
                                            if (_trackedMedia.indexOf(kids[k]) === -1) _trackedMedia.push(kids[k]);
                                        }
                                    }
                                    if (node.shadowRoot) _scanMediaElements(node.shadowRoot);
                                }
                            }
                        }
                    });
                    if (document.body) mo.observe(document.body, { childList: true, subtree: true });
                    else {
                        document.addEventListener('DOMContentLoaded', function() {
                            mo.observe(document.body, { childList: true, subtree: true });
                        });
                    }
                })();

                _scanMediaElements();

                function _bestMedia() {
                    for (var i = 0; i < _trackedMedia.length; i++) {
                        if (_trackedMedia[i].duration > 0 || _trackedMedia[i].currentTime > 0) return _trackedMedia[i];
                    }
                    if (_trackedMedia.length > 0) return _trackedMedia[0];
                    return null;
                }

                function log(level, msg) {
                    var full = '[sc-remote v' + VERSION + '] ' + msg;
                    if (level === 'error') console.error(full);
                    else if (level === 'warning') console.warn(full);
                    if (ws && ws.readyState === 1) {
                        try {
                            ws.send(JSON.stringify({ type: 'clientLog', level: level, message: msg }));
                        } catch (e) {}
                    }
                }

                function getState() {
                    var playButton = document.querySelector('.playControls__play');
                    var isPlaying = playButton ? playButton.classList.contains('playing') : false;

                    var artworkEl = document.querySelector('.playbackSoundBadge__avatar .image__lightOutline span');
                    var title = artworkEl ? (artworkEl.getAttribute('aria-label') || '') : '';
                    var artwork = '';
                    if (artworkEl) {
                        var bgImage = artworkEl.style.backgroundImage || '';
                        artwork = bgImage.replace(/^url\\(['"]?|['"]?\\)$/g, '');
                        artwork = artwork.replace(/-t\d+x\d+/g, '-t500x500');
                    }

                    var authorEl = document.querySelector('.playbackSoundBadge__lightLink');
                    var artist = authorEl ? authorEl.textContent.trim() : '';

                    var urlEl = document.querySelector('.playbackSoundBadge__titleLink');
                    var trackUrl = urlEl ? urlEl.href.split('?')[0] : '';

                    var vol = 0.5;
                    var m = _bestMedia();
                    if (m) vol = m.volume;
                    var progressMs = m ? Math.floor(m.currentTime * 1000) : 0;
                    var durationMs = m ? Math.floor(m.duration * 1000) : 0;

                    return {
                        type: 'scStateUpdate',
                        track: title,
                        artist: artist,
                        coverUrl: artwork,
                        id: trackUrl,
                        isPlaying: isPlaying,
                        progressMs: progressMs,
                        durationMs: durationMs,
                        volume: vol
                    };
                }

                function scSeek(positionMs) {
                    if (isNaN(positionMs) || positionMs < 0) return;
                    var m = _bestMedia();
                    if (m && m.duration > 0 && isFinite(m.duration)) {
                        var target = positionMs / 1000;
                        if (target > m.duration) target = m.duration;
                        m.currentTime = target;
                        log('info', 'Seek via media element: currentTime=' + target);
                        return;
                    }
                    log('info', 'No usable media element for seek, trying DOM...');
                    var ratio = Math.max(0, Math.min(1, positionMs / 300000));
                    log('info', 'Seeking via DOM at ratio=' + ratio.toFixed(4));
                    var el = document.querySelector('.playbackTimeline') || document.querySelector('.playbackTimeline__progressWrapper');
                    if (el) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0) {
                            ['pointerdown','pointerup','click','mousedown','mouseup'].forEach(function(t) {
                                el.dispatchEvent(new MouseEvent(t, {
                                    clientX: r.left + r.width * ratio, clientY: r.top + r.height / 2,
                                    bubbles: true, cancelable: true
                                }));
                            });
                            log('info', 'Dispatched events on timeline');
                        }
                    }
                }

                function scSetVolume(volume) {
                    volume = Math.max(0, Math.min(1, volume));
                    log('info', 'Setting volume to ' + volume.toFixed(3));
                    var m = _bestMedia();
                    if (m) {
                        m.volume = volume;
                        log('info', 'Volume set via media element');
                        return;
                    }
                    log('warning', 'No media element found — trying volume button');
                    var volBtn = document.querySelector('.volume');
                    if (volBtn) {
                        volBtn.click();
                        log('info', 'Clicked volume button');
                    }
                }

                function executeCommand(cmd) {
                    log('info', 'Executing command: ' + cmd.command);
                    switch (cmd.command) {
                        case 'togglePlay':
                        case 'play':
                        case 'pause':
                            var playBtn = document.querySelector('.playControl');
                            if (playBtn) { playBtn.click(); break; }
                            var m = _bestMedia();
                            if (m) { m.paused ? m.play() : m.pause(); }
                            break;
                        case 'next':
                            var next = document.querySelector('.skipControl__next');
                            if (next) next.click();
                            break;
                        case 'previous':
                            var prev = document.querySelector('.skipControl__previous');
                            if (prev) prev.click();
                            break;
                        case 'seek':
                            var seekMs = cmd.position_ms !== undefined ? cmd.position_ms : cmd.position;
                            if (seekMs !== undefined) scSeek(seekMs);
                            break;
                        case 'setVolume':
                            if (cmd.volume !== undefined) scSetVolume(cmd.volume);
                            break;
                        case 'like':
                            var likeBtn = document.querySelector('.playbackSoundBadge button.sc-button-like');
                            if (!likeBtn) likeBtn = document.querySelector('.playControls__soundBadge button.sc-button-like');
                            if (likeBtn) likeBtn.click();
                            break;
                    }
                }

                function debugDOM() {
                    log('info', '--- DOM Debug (v' + VERSION + ') ---');
                    log('info', 'tracked media elements: ' + _trackedMedia.length);
                    var best = _bestMedia();
                    log('info', 'best media: ' + (best ? (best.tagName + ' duration=' + (best.duration||0).toFixed(1) + ' ct=' + (best.currentTime||0).toFixed(1) + ' vol=' + (best.volume||0).toFixed(3)) : 'NONE'));
                    log('info', 'waveform: ' + (document.querySelector('.waveform') ? 'YES' : 'no'));
                    log('info', 'playbackTimeline: ' + (document.querySelector('.playbackTimeline') ? 'YES' : 'no'));
                    log('info', 'input[type=range]: ' + (document.querySelector('input[type="range"]') ? 'YES' : 'no'));
                    log('info', '.volume button: ' + (document.querySelector('.volume') ? 'YES' : 'no'));
                    log('info', '--- End DOM Debug ---');
                }

                // --- WebSocket ---
                function connect() {
                    try {
                        ws = new WebSocket(SERVER_URL);
                    } catch (e) {
                        log('error', 'WebSocket creation failed: ' + e.message);
                        scheduleReconnect();
                        return;
                    }

                    ws.onopen = function() {
                        log('info', 'Connected to server on port ' + SERVER_PORT);
                        reconnectDelay = 1000;
                        ws.send(JSON.stringify({ type: 'register', client: 'soundcloud' }));
                        debugDOM();
                        var state = getState();
                        log('info', 'Initial state - track: ' + state.track + ', playing: ' + state.isPlaying);
                        ws.send(JSON.stringify(state));
                        lastTrackUrl = state.id;
                        startPolling();
                    };

                    ws.onmessage = function(e) {
                        try {
                            var msg = JSON.parse(e.data);
                            if (msg.type === 'scPlaybackControl') {
                                log('info', 'Received command: ' + msg.command);
                                executeCommand(msg);
                                setTimeout(function() {
                                    if (ws && ws.readyState === 1) {
                                        ws.send(JSON.stringify(getState()));
                                    }
                                }, 400);
                            } else if (msg.type === 'scVolumeUpdate') {
                                log('info', 'Received volume update: ' + msg.volume);
                                scSetVolume(msg.volume);
                            } else if (msg.type === 'config') {
                                if (msg.pollingIntervalMs) {
                                    startPolling(msg.pollingIntervalMs);
                                }
                            }
                        } catch (err) {
                            log('error', 'Message parse error: ' + err.message);
                        }
                    };

                    ws.onclose = function() {
                        log('info', 'Disconnected, reconnecting...');
                        stopPolling();
                        scheduleReconnect();
                    };

                    ws.onerror = function() {};
                }

                function scheduleReconnect() {
                    var delay = Math.min(reconnectDelay * 2, MAX_RECONNECT);
                    reconnectDelay = delay;
                    setTimeout(connect, delay);
                }

                function startPolling(intervalMs) {
                    stopPolling();
                    var interval = intervalMs || 500;
                    pollInterval = setInterval(function() {
                        if (!ws || ws.readyState !== 1) return;
                        var state = getState();
                        ws.send(JSON.stringify(state));
                        if (state.id && state.id !== lastTrackUrl) {
                            lastTrackUrl = state.id;
                        }
                    }, interval);
                }

                function stopPolling() {
                    if (pollInterval) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                    }
                }

                // --- Init ---
                connect();

                window.__scrpc_cleanup_soundcloud_remote_bridge = function() {
                    stopPolling();
                    if (ws) {
                        ws.close();
                        ws = null;
                    }
                    delete window.__scRemoteLoaded;
                    log('info', 'Cleaned up');
                };
            })();
        `;
    },
};
