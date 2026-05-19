using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.WebsocketSend("{\"type\":\"like\"}", 0);
        CPH.SendMessage("❤️ Toggled like");
        return true;
    }
}
