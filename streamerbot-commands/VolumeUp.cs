using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"volumeUpdate\",\"command\":\"volumeUp\"}", 0);
        return true;
    }
}
