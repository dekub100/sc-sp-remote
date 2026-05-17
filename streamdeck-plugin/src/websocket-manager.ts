import WebSocket from "ws";
import { EventEmitter } from "events";
import http from "http";

export class WebSocketManager extends EventEmitter {
    private static instance: WebSocketManager | null = null;
    private websocket: WebSocket | null = null;
    private reconnectTimeout: NodeJS.Timeout | null = null;
    private port: number = 8888; // Default, will be updated
    private refCount: number = 0;
    private isConnecting: boolean = false;

    private constructor() {
        super();
    }

    public static getInstance(): WebSocketManager {
        if (!WebSocketManager.instance) {
            WebSocketManager.instance = new WebSocketManager();
        }
        return WebSocketManager.instance;
    }

    public connect() {
        this.refCount++;
        if (this.websocket && (this.websocket.readyState === WebSocket.OPEN || this.websocket.readyState === WebSocket.CONNECTING)) {
            return;
        }

        if (this.isConnecting) return;
        this.doConnect();
    }

    private async fetchConfig(): Promise<number> {
        return new Promise((resolve) => {
            http.get("http://localhost:54321/api/config", (res) => {
                let data = "";
                res.on("data", (chunk) => data += chunk);
                res.on("end", () => {
                    try {
                        const config = JSON.parse(data);
                        resolve(config.port || 8888);
                    } catch (e) {
                        resolve(8888);
                    }
                });
            }).on("error", () => {
                resolve(8888);
            });
        });
    }

    private async doConnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }

        this.isConnecting = true;
        this.port = await this.fetchConfig();

        this.websocket = new WebSocket(`ws://localhost:${this.port}/?client=streamdeck`);

        this.websocket.onopen = () => {
            this.isConnecting = false;
            this.emit("open");
        };

        this.websocket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data.toString());
                this.emit("message", data);
            } catch (e) {
                // Silently fail on parse error
            }
        };

        this.websocket.onclose = () => {
            this.isConnecting = false;
            this.emit("close");
            this.websocket = null;
            if (this.refCount > 0) {
                this.reconnectTimeout = setTimeout(() => this.doConnect(), 5000);
            }
        };

        this.websocket.onerror = (error) => {
            this.isConnecting = false;
            this.emit("error", error);
        };
    }

    public disconnect() {
        this.refCount--;
        if (this.refCount <= 0) {
            this.refCount = 0;
            if (this.reconnectTimeout) {
                clearTimeout(this.reconnectTimeout);
                this.reconnectTimeout = null;
            }
            if (this.websocket) {
                this.websocket.onclose = () => {};
                this.websocket.close();
                this.websocket = null;
            }
        }
    }

    private lastRequestTime: number = 0;

    public requestState() {
        const now = Date.now();
        if (now - this.lastRequestTime < 100) return; // Throttle requests
        this.lastRequestTime = now;
        this.send({ type: "getInitialState" });
    }

    public send(data: any) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(data));
        }
    }

    public get readyState(): number {
        return this.websocket ? this.websocket.readyState : WebSocket.CLOSED;
    }
}

export const wsManager = WebSocketManager.getInstance();
