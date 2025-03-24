@echo off
nuitka --onefile --standalone --enable-plugin=pyqt5 --remove-output --include-data-files=style.css=style.css --windows-icon-from-ico=ICON.ico --include-data-dir=media=media --windows-console-mode=disable --output-dir=dist amp.py
pause