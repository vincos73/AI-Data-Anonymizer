import os

application = "OMISSIS.app"
app_path = os.path.join(os.getcwd(), "dist", application)

files = [app_path]
symlinks = {"Applications": "/Applications"}

icon_locations = {
    application: (140, 120),
    "Applications": (420, 120),
}

window_rect = ((100, 100), (560, 320))
icon_size = 96
text_size = 12
format = "UDZO"
