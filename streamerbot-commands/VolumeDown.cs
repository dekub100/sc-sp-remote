using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"volumeUpdate\",\"command\":\"volumeDown\"}", 0);
        CPH.SendMessage("🔉 Volume down");
        return true;
    }
}
