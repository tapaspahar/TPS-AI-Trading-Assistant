def get_dark_theme():
    return """
    QWidget{
        background-color:#0f172a;
        color:white;
        font-family:Segoe UI;
        font-size:11pt;
    }

    QFrame#sidebar{
        background-color:#1e293b;
        border-right:1px solid #334155;
    }

    QFrame#header{
        background-color:#16213e;
        border-bottom:1px solid #334155;
    }

    QPushButton{
        background-color:transparent;
        color:white;
        padding:10px;
        border:none;
        text-align:left;
    }

    QPushButton:hover{
        background:#334155;
        border-radius:8px;
    }

    QLabel#title{
        font-size:20px;
        font-weight:bold;
    }

    QLabel#subtitle{
        color:#94a3b8;
    }
    """