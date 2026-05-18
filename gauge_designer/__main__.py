import sys
from PySide6.QtWidgets import QApplication
from gauge_designer.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("pyXplane Panels Designer")
    app.setOrganizationName("pySTXPlanePanels")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
