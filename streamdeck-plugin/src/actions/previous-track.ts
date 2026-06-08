import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type PreviousTrackSettings = {
  source?: string;
};

@action({ UUID: "com.dekub.spicetify-remote.previoustrack" })
export class PreviousTrack extends SingletonAction<PreviousTrackSettings> {
  override onWillAppear(ev: WillAppearEvent<PreviousTrackSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<PreviousTrackSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "previous" });
    } else {
      wsManager.send({ type: "playbackControl", command: "previous" });
    }
  }
}
