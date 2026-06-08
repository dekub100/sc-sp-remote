import { action, KeyUpEvent, SingletonAction, WillAppearEvent, WillDisappearEvent, DidReceiveSettingsEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type VolumeUpSettings = {
  source?: string;
  step?: number;
};

@action({ UUID: "com.dekub.sc-sp-remote.volumeup" })
export class VolumeUp extends SingletonAction<VolumeUpSettings> {
  override onWillAppear(ev: WillAppearEvent<VolumeUpSettings>): void | Promise<void> {
    wsManager.connect();
  }

  override onWillDisappear(): void | Promise<void> {
    wsManager.disconnect();
  }

  override async onKeyUp(ev: KeyUpEvent<VolumeUpSettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;
    const step = ev.payload.settings.step || 0.05;
    if (effectiveSource === "soundcloud") {
      wsManager.send({ type: "scVolumeUpdate", command: "volumeUp", step });
    } else {
      wsManager.send({ type: "volumeUpdate", command: "volumeUp", step });
    }
  }
}
