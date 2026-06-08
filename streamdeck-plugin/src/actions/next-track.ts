import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type NextTrackSettings = {
  source?: string;
};

@action({ UUID: "com.dekub.spicetify-remote.nexttrack" })
export class NextTrack extends SingletonAction<NextTrackSettings> {
  override onWillAppear(ev: WillAppearEvent<NextTrackSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<NextTrackSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scPlaybackControl", command: "next" });
    } else {
      wsManager.send({ type: "playbackControl", command: "next" });
    }
  }
}
