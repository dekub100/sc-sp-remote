import streamDeck from "@elgato/streamdeck";

import { PlayPause } from "./actions/play-pause";
import { NextTrack } from "./actions/next-track";
import { PreviousTrack } from "./actions/previous-track";
import { VolumeUp } from "./actions/volume-up";
import { VolumeDown } from "./actions/volume-down";
import { ToggleShuffle } from "./actions/toggle-shuffle";
import { ToggleRepeat } from "./actions/toggle-repeat";
import { ToggleLike } from "./actions/toggle-like";
import { VolumeDisplay } from "./actions/volume-display";
import { SetVolume } from "./actions/set-volume";
import { wsManager } from "./websocket-manager";

// We can enable "trace" logging so that all messages between the Stream Deck, and the plugin are recorded. When storing sensitive information
streamDeck.logger.setLevel("trace");

// Apply global port setting across all actions.
streamDeck.settings.onDidReceiveGlobalSettings(({ settings }) => {
    if (settings.port) {
        wsManager.setPort(settings.port as number);
    }
});

// Fetch saved port on startup.
streamDeck.settings.getGlobalSettings().then((settings) => {
    if (settings.port) {
        wsManager.setPort(settings.port as number);
    }
});

// Register the actions.
streamDeck.actions.registerAction(new PlayPause());
streamDeck.actions.registerAction(new NextTrack());
streamDeck.actions.registerAction(new PreviousTrack());
streamDeck.actions.registerAction(new VolumeUp());
streamDeck.actions.registerAction(new VolumeDown());
streamDeck.actions.registerAction(new ToggleShuffle());
streamDeck.actions.registerAction(new ToggleRepeat());
streamDeck.actions.registerAction(new ToggleLike());
streamDeck.actions.registerAction(new VolumeDisplay());
streamDeck.actions.registerAction(new SetVolume());

// Finally, connect to the Stream Deck.
streamDeck.connect();
