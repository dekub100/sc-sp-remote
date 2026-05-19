using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"clearQueue\",\"requestedBy\":\"streamer.bot\"}", 0);
        CPH.SendMessage("🗑️ Queue cleared!");
        CPH.LogInfo("ClearQueue: Queue cleared");
        return true;
    }
}
