import { action, KeyAction, SingletonAction, WillAppearEvent, WillDisappearEvent, DidReceiveSettingsEvent, KeyUpEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

type VolumeDisplaySettings = {
  source?: string;
};

@action({ UUID: "com.dekub.sc-sp-remote.volumedisplay" })
export class VolumeDisplay extends SingletonAction<VolumeDisplaySettings> {
  private _volume: number = -1;
  private _isMuted: boolean = false;
  private _previousVolume: number = 50;
  private actionInstances: Map<string, KeyAction<VolumeDisplaySettings>> = new Map();
  private actionSources: Map<string, string> = new Map();
  private pollingInterval: NodeJS.Timeout | null = null;

  private handleMessage = (data: any) => {
    this.actionInstances.forEach((action, id) => {
      const source = this.actionSources.get(id) || "spotify";
      const effectiveSource = source === "auto" ? wsManager.activeSource : source;
      if (data.source === effectiveSource && typeof data.volume === "number") {
        this._volume = Math.round(data.volume * 100);
        if (this._isMuted && data.volume > 0) {
          this._isMuted = false;
        }
        this.updateButtonAppearance();
      }
    });
  };

  override async onWillAppear(ev: WillAppearEvent<VolumeDisplaySettings>): Promise<void> {
    this.actionInstances.set(ev.action.id, ev.action as KeyAction<VolumeDisplaySettings>);
    const settings = await ev.action.getSettings();
    this.actionSources.set(ev.action.id, settings.source || "spotify");

    wsManager.connect();
    wsManager.off("message", this.handleMessage);
    wsManager.on("message", this.handleMessage);

    if (!this.pollingInterval) {
      this.pollingInterval = setInterval(() => {
        if (wsManager.readyState === 1) {
          wsManager.requestState();
        }
      }, 15000);
    }

    if (wsManager.readyState === 1) {
        wsManager.requestState();
    } else {
        wsManager.once("open", () => wsManager.requestState());
    }

    this.updateButtonAppearance();
  }

  override onWillDisappear(ev: WillDisappearEvent<VolumeDisplaySettings>): void | Promise<void> {
    this.actionInstances.delete(ev.action.id);
    this.actionSources.delete(ev.action.id);
    if (this.actionInstances.size === 0) {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
      wsManager.off("message", this.handleMessage);
      wsManager.disconnect();
    }
  }

  override onDidReceiveSettings(ev: DidReceiveSettingsEvent<VolumeDisplaySettings>): void {
    this.actionSources.set(ev.action.id, ev.payload.settings.source || "spotify");
  }

  override async onKeyUp(ev: KeyUpEvent<VolumeDisplaySettings>): Promise<void> {
    const source = ev.payload.settings.source || "spotify";
    const effectiveSource = source === "auto" ? wsManager.activeSource : source;

    if (this._isMuted) {
      this._isMuted = false;
      const vol = this._previousVolume / 100;
      this._volume = this._previousVolume;
      this.updateButtonAppearance();
      if (effectiveSource === "soundcloud") {
        wsManager.send({ type: "scVolumeUpdate", volume: vol });
      } else {
        wsManager.send({ type: "volumeUpdate", volume: vol });
      }
    } else {
      this._isMuted = true;
      this._previousVolume = this._volume > 0 ? this._volume : 50;
      this._volume = 0;
      this.updateButtonAppearance();
      if (effectiveSource === "soundcloud") {
        wsManager.send({ type: "scVolumeUpdate", volume: 0 });
      } else {
        wsManager.send({ type: "volumeUpdate", volume: 0 });
      }
    }
  }

  private updateButtonAppearance() {
    const displayText = this._isMuted ? "MUTED" : (this._volume === -1 ? "--" : `${this._volume}%`);
    this.actionInstances.forEach(actionInstance => {
      actionInstance.setTitle(displayText);
    });
  }
}
