import streamDeck from "@elgato/streamdeck";

import { PlayPause } from "./actions/play-pause";
import { NextTrack } from "./actions/next-track";
import { PreviousTrack } from "./actions/previous-track";
import { SeekForward } from "./actions/seek-forward";
import { SeekBack } from "./actions/seek-back";
import { VolumeUp } from "./actions/volume-up";
import { VolumeDown } from "./actions/volume-down";
import { ToggleShuffle } from "./actions/toggle-shuffle";
import { ToggleRepeat } from "./actions/toggle-repeat";
import { ToggleLike } from "./actions/toggle-like";
import { VolumeDisplay } from "./actions/volume-display";
import { SetVolume } from "./actions/set-volume";
import { wsManager } from "./websocket-manager";

streamDeck.logger.setLevel("info");

streamDeck.settings.onDidReceiveGlobalSettings(({ settings }) => {
    if (settings.port) {
        wsManager.setPort(settings.port as number);
    }
});

streamDeck.settings.getGlobalSettings().then((settings) => {
    if (settings.port) {
        wsManager.setPort(settings.port as number);
    }
});

function pushConnectionState(connected: boolean) {
    streamDeck.settings.getGlobalSettings().then((settings) => {
        streamDeck.settings.setGlobalSettings({ ...settings, connected });
    });
}

wsManager.on("open", () => pushConnectionState(true));
wsManager.on("close", () => pushConnectionState(false));

streamDeck.actions.registerAction(new PlayPause());
streamDeck.actions.registerAction(new NextTrack());
streamDeck.actions.registerAction(new PreviousTrack());
streamDeck.actions.registerAction(new SeekForward());
streamDeck.actions.registerAction(new SeekBack());
streamDeck.actions.registerAction(new VolumeUp());
streamDeck.actions.registerAction(new VolumeDown());
streamDeck.actions.registerAction(new ToggleShuffle());
streamDeck.actions.registerAction(new ToggleRepeat());
streamDeck.actions.registerAction(new ToggleLike());
streamDeck.actions.registerAction(new VolumeDisplay());
streamDeck.actions.registerAction(new SetVolume());

streamDeck.connect();
