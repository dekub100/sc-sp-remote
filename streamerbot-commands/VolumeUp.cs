using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"volumeUpdate\",\"command\":\"volumeUp\"}", 0);
        CPH.SendMessage("🔊 Volume up");
        return true;
    }
}
