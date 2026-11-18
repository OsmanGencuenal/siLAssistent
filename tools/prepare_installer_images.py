"""Create Inno wizard bitmaps from the selected Support.ico, outside the runtime package."""
import os
import sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QRect
from PySide6.QtGui import QIcon,QImage,QPainter,QColor
from PySide6.QtWidgets import QApplication

class InstallerImages:
    @classmethod
    def create(cls,icon_file,destination):
        app=QApplication.instance() or QApplication([])
        icon=QIcon(str(icon_file))
        if icon.isNull():raise ValueError("Support.ico kann nicht geladen werden.")
        destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
        for name,width,height,size in (("wizard.bmp",164,314,144),("wizard-small.bmp",55,55,49)):
            image=QImage(width,height,QImage.Format.Format_RGB32)
            image.fill(QColor("#f6f8fb" if name=="wizard.bmp" else "#ffffff"))
            painter=QPainter(image)
            icon.paint(painter,QRect((width-size)//2,(height-size)//2,size,size))
            painter.end()
            if not image.save(str(destination/name),"BMP"):raise OSError("Installerbild konnte nicht gespeichert werden.")
        return destination

if __name__=="__main__":InstallerImages.create(sys.argv[1],sys.argv[2])
