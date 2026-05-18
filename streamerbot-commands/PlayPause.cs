using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"playbackControl\",\"command\":\"togglePlay\"}", 0);
        return true;
    }
}
