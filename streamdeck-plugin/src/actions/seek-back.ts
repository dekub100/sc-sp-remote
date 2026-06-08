import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent, DidReceiveSettingsEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type SeekBackSettings = {
  source?: string;
  seconds?: number;
};

@action({ UUID: "com.dekub.sc-sp-remote.seekback" })
export class SeekBack extends SingletonAction<SeekBackSettings> {
  override onWillAppear(ev: WillAppearEvent<SeekBackSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<SeekBackSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    const offset = (ev.payload.settings.seconds || 10) * 1000;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "seekBack", offset });
    } else {
      wsManager.send({ type: "playbackControl", command: "seekBack", offset });
    }
  }
}
