import { action, KeyAction, SingletonAction, WillAppearEvent, WillDisappearEvent } from "@elgato/streamdeck";
import { wsManager } from "../websocket-manager";

@action({ UUID: "com.dekub.spicetify-remote.volumedisplay" })
export class VolumeDisplay extends SingletonAction {
  private currentVolume: number = -1; // -1 indicates uninitialized
  private actionInstances: Map<string, KeyAction> = new Map(); // Store KeyAction instances by ID
  private pollingInterval: NodeJS.Timeout | null = null;

  private handleMessage = (data: any) => {
    if (typeof data.volume === "number") {
      this.currentVolume = Math.round(data.volume * 100); // Convert to percentage
      this.updateButtonAppearance();
    }
  };

  override onWillAppear(ev: WillAppearEvent): void | Promise<void> {
    this.actionInstances.set(ev.action.id, ev.action as KeyAction);
    
    // Always ensure connection and listener
    wsManager.connect();
    wsManager.off("message", this.handleMessage); // Prevent duplicates
    wsManager.on("message", this.handleMessage);

    // Start polling fallback if not already started
    if (!this.pollingInterval) {
      this.pollingInterval = setInterval(() => {
        if (wsManager.readyState === 1) {
          wsManager.requestState();
        }
      }, 15000); // 15 second fallback poll
    }
    
    // Immediate state request
    if (wsManager.readyState === 1) {
        wsManager.requestState();
    } else {
        wsManager.once("open", () => wsManager.requestState());
    }

    this.updateButtonAppearance();
  }

  override onWillDisappear(ev: WillDisappearEvent): void | Promise<void> {
    this.actionInstances.delete(ev.action.id);
    if (this.actionInstances.size === 0) {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
      wsManager.off("message", this.handleMessage);
      wsManager.disconnect();
    }
  }

  private updateButtonAppearance() {
    const displayVolume = this.currentVolume === -1 ? "--" : `${this.currentVolume}%`;
    this.actionInstances.forEach(actionInstance => {
      actionInstance.setTitle(displayVolume);
    });
  }
}