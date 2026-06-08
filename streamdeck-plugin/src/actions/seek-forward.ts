import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent, DidReceiveSettingsEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type SeekForwardSettings = {
  source?: string;
  seconds?: number;
};

@action({ UUID: "com.dekub.spicetify-remote.seekforward" })
export class SeekForward extends SingletonAction<SeekForwardSettings> {
  override onWillAppear(ev: WillAppearEvent<SeekForwardSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<SeekForwardSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    const offset = (ev.payload.settings.seconds || 10) * 1000;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "seekForward", offset });
    } else {
      wsManager.send({ type: "playbackControl", command: "seekForward", offset });
    }
  }
}
