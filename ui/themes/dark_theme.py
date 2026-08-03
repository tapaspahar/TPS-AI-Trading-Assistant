def get_dark_theme():
    return """

QWidget{
    background:#0f172a;
    color:white;
    font-family:Segoe UI;
    font-size:11pt;
}

QFrame#sidebar{
    background:#1e293b;
    border-right:1px solid #334155;
}

QFrame#header{
    background:#16213e;
    border-bottom:1px solid #334155;
}

QLabel#title{
    font-size:22px;
    font-weight:bold;
    color:white;
}

QLabel#subtitle{
    color:#94a3b8;
}

QLabel#status{
    color:#4ade80;
    font-size:12pt;
}

QLabel#clock{
    color:#38bdf8;
    font-weight:bold;
}

QLabel#user{
    color:white;
}

QPushButton{
    background:transparent;
    border:none;
    padding:10px;
    text-align:left;
}

QPushButton:hover{
    background:#334155;
    border-radius:8px;
}

QFrame#dashboardCard{

background:#1f2a44;

border:1px solid #394867;

border-radius:18px;

padding:15px;

}

QFrame#dashboardCard:hover{

border:2px solid #4da3ff;

}

QLabel#cardTitle{

font-size:14px;

color:#b8c7e0;

}

QLabel#cardValue{

font-size:30px;

font-weight:bold;

color:white;

}

QLabel#cardValue[density="compact"]{

font-size:18px;

}

QPushButton#menuButton{

    background:transparent;

    color:white;

    padding:12px;

    border:none;

    border-radius:8px;

    text-align:left;

    font-size:11pt;

}

QPushButton#menuButton:hover{

    background:#334155;

}

QPushButton#menuButton:pressed{

    background:#2563eb;

}
"""
