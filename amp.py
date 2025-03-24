""" Import the necessary modules for the program to work """
import sys
import os
import urllib.request
import zipfile
from PyQt5.QtWidgets import QApplication, QProgressDialog
from PyQt5.QtCore import Qt



""" Download necessary VLC dependencies """
def setup_vlc_dependencies():
    appdata = os.environ.get("APPDATA")
    vlc_base = os.path.join(appdata, "ravendevteam", "amp", "vlc")
    required_files = ["libvlc.dll", "libvlccore.dll"]
    dll_path = None
    if os.path.exists(vlc_base):
        for root, dirs, files in os.walk(vlc_base):
            if all(dll in files for dll in required_files):
                dll_path = root
                break

    if dll_path:
        os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
        print("VLC dependencies already present in:", dll_path)
        return
    os.makedirs(vlc_base, exist_ok=True)
    app_created = False
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        app_created = True
    progress = QProgressDialog("Downloading dependencies...", "Cancel", 0, 100)
    progress.setWindowTitle("Amp Setup")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    progress.show()

    def reporthook(block_num, block_size, total_size):
        if total_size > 0:
            downloaded = block_num * block_size
            percent = min(int(downloaded * 100 / total_size), 100)
            progress.setValue(percent)
            QApplication.processEvents()
            if progress.wasCanceled():
                raise Exception("Download canceled by user")

    url = "https://download.videolan.org/pub/videolan/vlc/3.0.18/win64/vlc-3.0.18-win64.zip"
    zip_path = os.path.join(vlc_base, "vlc.zip")
    try:
        urllib.request.urlretrieve(url, zip_path, reporthook)
        progress.setLabelText("Extracting dependencies...")
        QApplication.processEvents()
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(vlc_base)
        dll_path = None
        for root, dirs, files in os.walk(vlc_base):
            if all(dll in files for dll in required_files):
                dll_path = root
                break
        if dll_path:
            os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")
            print("VLC dependencies set up successfully in:", dll_path)
        else:
            raise FileNotFoundError("VLC DLLs not found after extraction.")
    except Exception as e:
        progress.cancel()
        print("Error downloading or extracting VLC dependencies:", e)
    finally:
        progress.setValue(100)
        QApplication.processEvents()
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if app_created:
            app.exit()



setup_vlc_dependencies()
import importlib.util
import vlc
from PyQt5.QtCore import Qt, QUrl, QTimer, QModelIndex, QSettings, QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QFontMetrics
from PyQt5.QtWidgets import (
    QMainWindow, QAction, QWidget, QVBoxLayout, QHBoxLayout, QDockWidget, QTreeView, 
    QFileDialog, QFileSystemModel, QPushButton, QSlider, QLabel, QStatusBar, 
    QSystemTrayIcon, QMenu, QProgressDialog
)
try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None



""" Create a class for the VLC backend """
class VLCMediaPlayer(QObject):
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    mediaEnded = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self._duration = 0
        self._current_media = None
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(500)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start()
        events = self.player.event_manager()
        events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_media_end)

    def _poll(self):
        duration = self.player.get_length()
        if duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        pos = self.player.get_time()
        self.positionChanged.emit(pos)

    def set_media(self, file_path):
        media = self.instance.media_new(file_path)
        self.player.set_media(media)
        self._current_media = file_path

    def _on_media_end(self, event):
        self.mediaEnded.emit()

    def play(self):
        self.player.play()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def set_position(self, position):
        duration = self.get_duration()
        if duration > 0:
            fraction = position / duration
            self.player.set_position(fraction)

    def get_position(self):
        return self.player.get_time()

    def get_duration(self):
        return self.player.get_length()

    def set_volume(self, volume):
        self.player.audio_set_volume(volume)

    def is_playing(self):
        return self.player.is_playing()



""" Utility function to load plugins """
def load_plugins(app_context):
    user_home = os.path.expanduser("~")
    plugins_dir = os.path.join(user_home, "ampplugins")
    os.makedirs(plugins_dir, exist_ok=True)
    loaded_plugins = []
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            plugin_path = os.path.join(plugins_dir, filename)
            mod_name = os.path.splitext(filename)[0]
            spec = importlib.util.spec_from_file_location(mod_name, plugin_path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
                if hasattr(module, "register_plugin"):
                    module.register_plugin(app_context)
                    loaded_plugins.append(mod_name)
                    print(f"Plugin '{mod_name}' loaded successfully from {plugins_dir}")
            except Exception as e:
                print(f"Failed to load plugin '{filename}' from {plugins_dir}: {e}")
    return loaded_plugins



""" Utility function to load the stylesheet """
def loadStyle():
    user_css_path = os.path.join(os.path.expanduser("~"), "apstyle.css")
    stylesheet = None
    if os.path.exists(user_css_path):
        try:
            with open(user_css_path, 'r') as css_file:
                stylesheet = css_file.read()
            print(f"Loaded user CSS style from: {user_css_path}")
        except Exception as e:
            print(f"Error loading user CSS: {e}")
    else:
        css_file_path = os.path.join(os.path.dirname(__file__), 'style.css')
        try:
            with open(css_file_path, 'r') as css_file:
                stylesheet = css_file.read()
        except FileNotFoundError:
            print(f"Default CSS file not found: {css_file_path}")
    if stylesheet:
        app = QApplication.instance()
        if app:
            app.setStyleSheet(stylesheet)
        else:
            print("No QApplication instance found. Stylesheet not applied.")



""" Create a class for the main window """
class MusicPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Amp")
        self.setGeometry(100, 100, 1000, 600)
        self.always_on_top = False
        loadStyle()
        self.setWindowIcon(self.get_app_icon())
        self.init_ui()
        self.mediaPlayer = VLCMediaPlayer(self)
        self.current_index = 0
        app_context = {"main_window": self}
        self.plugins = load_plugins(app_context)
        self.loop_mode = 0
        self.shuffle = False
        self.folderAudioFiles = []
        self.trackMetadata = {}
        self.setup_dock()
        self.setup_main_ui()
        self.setup_actions()
        self.setup_connections()
        self.updatePlaybackMode()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_position)
        self.timer.start()
        self.settings = QSettings("Raven", "Amp")
        self.setup_view_menu()
        self.trayIcon = None
        self.update_slider = True

    def init_ui(self):
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        main_widget.setLayout(self.main_layout)
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

    def setup_view_menu(self):
        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("View")
        minimize_action = QAction("Minimize to Tray", self)
        minimize_action.triggered.connect(self.minimize_to_tray)
        view_menu.addAction(minimize_action)
        self.minimizeOnCloseAction = QAction("Closing Window Minimizes to Tray", self, checkable=True)
        self.minimizeOnCloseAction.setChecked(self.settings.value("closeToTray", False, type=bool))
        self.minimizeOnCloseAction.toggled.connect(lambda checked: self.settings.setValue("closeToTray", checked))
        view_menu.addAction(self.minimizeOnCloseAction)

    def create_tray_icon(self):
        media_path = self.get_media_folder_path()
        tray_icon_path = os.path.join(media_path, 'tray.png')
        if not os.path.exists(tray_icon_path):
            print(f"Tray icon file not found: {tray_icon_path}")
        self.trayIcon = QSystemTrayIcon(QIcon(tray_icon_path), self)
        self.trayMenu = QMenu()
        self.trayPlayPauseAction = QAction("Play/Pause", self)
        self.trayPlayPauseAction.triggered.connect(self.play_pause)
        self.trayMenu.addAction(self.trayPlayPauseAction)
        self.trayNextAction = QAction("Next", self)
        self.trayNextAction.triggered.connect(self.next_track)
        self.trayMenu.addAction(self.trayNextAction)
        self.trayPreviousAction = QAction("Previous", self)
        self.trayPreviousAction.triggered.connect(self.previous_track)
        self.trayMenu.addAction(self.trayPreviousAction)
        self.trayShuffleAction = QAction("Shuffle", self)
        self.trayShuffleAction.triggered.connect(self.toggle_shuffle)
        self.trayMenu.addAction(self.trayShuffleAction)
        self.trayLoopAction = QAction("Loop", self)
        self.trayLoopAction.triggered.connect(self.toggle_loop)
        self.trayMenu.addAction(self.trayLoopAction)
        self.trayIcon.setContextMenu(self.trayMenu)
        self.trayIcon.activated.connect(self.on_tray_icon_activated)
        self.trayIcon.show()

    def minimize_to_tray(self):
        if self.trayIcon is None:
            self.create_tray_icon()
        self.hide()
        self.trayIcon.showMessage("Amp", "Amp minimized to tray", QSystemTrayIcon.Information, 2000)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.showNormal()
            self.activateWindow()
            self.trayIcon.hide()
            self.trayIcon.deleteLater()
            self.trayIcon = None

    def closeEvent(self, event):
        if self.minimizeOnCloseAction.isChecked():
            event.ignore()
            self.minimize_to_tray()
        else:
            event.accept()

    def get_app_icon(self):
        base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
        icon_path = os.path.join(base_path, 'ICON.ico')
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        else:
            print(f"Icon file not found: {icon_path}")
            return QIcon()

    def get_media_folder_path(self):
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(__file__)
        return os.path.join(base_path, 'media')

    def handle_media_ended(self):
        if self.loop_mode == 2:
            self.mediaPlayer.set_media(self.folderAudioFiles[self.current_index])
            self.mediaPlayer.play()
        elif self.shuffle:
            import random
            self.current_index = random.randint(0, len(self.folderAudioFiles) - 1)
            self.mediaPlayer.set_media(self.folderAudioFiles[self.current_index])
            self.mediaPlayer.play()
        else:
            self.current_index += 1
            if self.current_index >= len(self.folderAudioFiles):
                if self.loop_mode == 1:
                    self.current_index = 0
                else:
                    self.current_index -= 1
                    self.mediaPlayer.stop()
                    self.playButton.setIcon(self.play_icon)
                    return
            self.mediaPlayer.set_media(self.folderAudioFiles[self.current_index])
            self.mediaPlayer.play()
        self.updateTrackInfo()

    def extractMetadata(self, file_path):
        if MutagenFile is None:
            return {
                'title': None,
                'artist': None,
                'album': None,
                'year': None,
                'artwork': None,
                'track': None
            }
        try:
            audio = MutagenFile(file_path)
            if not audio or not audio.tags:
                return {
                    'title': None,
                    'artist': None,
                    'album': None,
                    'year': None,
                    'artwork': None,
                    'track': None
                }
            title, artist, album, year, artwork_data, track = None, None, None, None, None, None
            for tag in audio.tags.keys():
                if tag.startswith('TIT2'):
                    title = str(audio.tags[tag])
                elif tag.startswith('TPE1'):
                    artist = str(audio.tags[tag])
                elif tag.startswith('TALB'):
                    album = str(audio.tags[tag])
                elif tag.startswith('TDRC') or tag.startswith('TYER'):
                    year = str(audio.tags[tag])
                elif tag.startswith('APIC'):
                    artwork_data = audio.tags[tag].data
                elif tag.startswith('TRCK'):
                    try:
                        track_str = str(audio.tags[tag])
                        track = track_str.split('/')[0].strip()
                    except Exception:
                        track = None
            return {
                'title': title,
                'artist': artist,
                'album': album,
                'year': year,
                'artwork': artwork_data,
                'track': track
            }
        except Exception:
            return {
                'title': None,
                'artist': None,
                'album': None,
                'year': None,
                'artwork': None,
                'track': None
            }

    def updateTrackInfo(self):
        current_file = self.folderAudioFiles[self.current_index]
        meta = self.extractMetadata(current_file)
        self.trackMetadata[self.current_index] = meta
        title = meta.get('title') or os.path.basename(current_file)
        artist = meta.get('artist') or "Unknown Artist"
        album = meta.get('album') or "Unknown Album"
        year = meta.get('year') or ""
        artwork_data = meta.get('artwork')
        self.titleLabel.setText(title)
        self.authorLabel.setText(artist)
        self.albumLabel.setText(album)
        self.yearLabel.setText(year)
        if artwork_data:
            pixmap = QPixmap()
            pixmap.loadFromData(artwork_data)
            pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.artLabel.setPixmap(pixmap)
        else:
            media_path = self.get_media_folder_path()
            placeholder_path = os.path.join(media_path, "albumartplaceholder.png")
            if os.path.exists(placeholder_path):
                pixmap = QPixmap(placeholder_path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.artLabel.setPixmap(pixmap)
            else:
                self.artLabel.setText("No Art")
                self.artLabel.setStyleSheet("border: 1px solid #999; color: gray;")
        self.update_status_bar()

    def setup_dock(self):
        self.fileDock = QDockWidget("File Explorer", self)
        self.fileDock.setObjectName("FileExplorerDock")
        self.fileDock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        self.fileModel = QFileSystemModel()
        self.fileModel.setReadOnly(True)
        self.fileTreeView = QTreeView()
        self.fileTreeView.setModel(self.fileModel)
        self.fileDock.setWidget(self.fileTreeView)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.fileDock)
        self.fileDock.hide()

    def setup_main_ui(self):
        media_path = self.get_media_folder_path()
        top_container = QWidget()
        top_layout = QHBoxLayout(top_container)
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(15)
        self.artLabel = QLabel()
        self.artLabel.setFixedSize(200, 200)
        self.artLabel.setAlignment(Qt.AlignCenter)
        placeholder_path = os.path.join(media_path, "albumartplaceholder.png")
        if os.path.exists(placeholder_path):
            pm = QPixmap(placeholder_path).scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.artLabel.setPixmap(pm)
        else:
            self.artLabel.setText("No Art")
            self.artLabel.setStyleSheet("border: 1px solid #999; color: gray;")
        top_layout.addWidget(self.artLabel, alignment=Qt.AlignTop)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(5)
        self.titleLabel = QLabel("Select a song to begin")
        self.titleLabel.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.titleLabel.setWordWrap(False)
        info_layout.addWidget(self.titleLabel)
        self.authorLabel = QLabel("")
        self.authorLabel.setStyleSheet("font-size: 13px;")
        self.authorLabel.setWordWrap(False)
        info_layout.addWidget(self.authorLabel)
        self.albumLabel = QLabel("")
        self.albumLabel.setStyleSheet("font-size: 13px;")
        self.albumLabel.setWordWrap(False)
        info_layout.addWidget(self.albumLabel)
        self.yearLabel = QLabel("")
        self.yearLabel.setStyleSheet("font-size: 13px;")
        self.yearLabel.setWordWrap(False)
        info_layout.addWidget(self.yearLabel)
        info_layout.addStretch(1)
        top_layout.addLayout(info_layout)
        self.main_layout.addWidget(top_container)
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(5, 5, 5, 5)
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(15)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        media_controls_widget = QWidget()
        media_controls_layout = QHBoxLayout(media_controls_widget)
        media_controls_layout.setSpacing(15)
        media_controls_layout.setContentsMargins(0, 0, 0, 0)
        self.shuffleButton = QPushButton("Off")
        self.shuffleButton.setIcon(QIcon(os.path.join(media_path, "shuffle.png")))
        media_controls_layout.addWidget(self.shuffleButton)
        self.prevButton = QPushButton()
        self.prevButton.setIcon(QIcon(os.path.join(media_path, "prev.png")))
        self.prevButton.setToolTip("Previous")
        media_controls_layout.addWidget(self.prevButton)
        self.playButton = QPushButton()
        self.play_icon = QIcon(os.path.join(media_path, "play.png"))
        self.pause_icon = QIcon(os.path.join(media_path, "pause.png"))
        self.playButton.setIcon(self.play_icon)
        self.playButton.setToolTip("Play/Pause")
        media_controls_layout.addWidget(self.playButton)
        self.nextButton = QPushButton()
        self.nextButton.setIcon(QIcon(os.path.join(media_path, "next.png")))
        self.nextButton.setToolTip("Next")
        media_controls_layout.addWidget(self.nextButton)
        self.loopButton = QPushButton("Off")
        self.loopButton.setToolTip("Loop")
        self.loopButton.setIcon(QIcon(os.path.join(media_path, "loop.png")))
        media_controls_layout.addWidget(self.loopButton)
        media_controls_layout.setAlignment(Qt.AlignCenter)
        controls_layout.addWidget(media_controls_widget, stretch=1, alignment=Qt.AlignCenter)
        volume_icon = QIcon(os.path.join(media_path, "volume.png"))
        self.volumeLabel = QLabel()
        self.volumeLabel.setPixmap(volume_icon.pixmap(24, 24))
        self.volumeSlider = QSlider(Qt.Horizontal)
        self.volumeSlider.setRange(0, 100)
        self.volumeSlider.setValue(50)
        controls_layout.addWidget(self.volumeLabel, alignment=Qt.AlignRight)
        controls_layout.addWidget(self.volumeSlider, alignment=Qt.AlignRight)
        bottom_layout.addLayout(controls_layout)
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(10)
        self.timeElapsedLabel = QLabel("0:00")
        self.positionSlider = QSlider(Qt.Horizontal)
        self.positionSlider.setObjectName("progressBar")
        self.positionSlider.setRange(0, 0)
        self.timeRemainingLabel = QLabel("0:00")
        progress_layout.addWidget(self.timeElapsedLabel)
        progress_layout.addWidget(self.positionSlider, stretch=1)
        progress_layout.addWidget(self.timeRemainingLabel)
        bottom_layout.addLayout(progress_layout)
        self.main_layout.addWidget(bottom_container)

    def setup_actions(self):
        menu_bar = self.menuBar()
        media_menu = menu_bar.addMenu("Media")
        openFileAction = QAction("Open File", self)
        openFileAction.triggered.connect(self.open_file)
        media_menu.addAction(openFileAction)
        openFolderAction = QAction("Open Folder", self)
        openFolderAction.triggered.connect(self.open_folder)
        media_menu.addAction(openFolderAction)

    def setup_connections(self):
        if self.mediaPlayer:
            self.mediaPlayer.positionChanged.connect(self.on_position_changed)
            self.mediaPlayer.durationChanged.connect(self.on_duration_changed)
            self.mediaPlayer.mediaEnded.connect(self.handle_media_ended)
        self.playButton.clicked.connect(self.play_pause)
        self.prevButton.clicked.connect(self.previous_track)
        self.nextButton.clicked.connect(self.next_track)
        self.shuffleButton.clicked.connect(self.toggle_shuffle)
        self.loopButton.clicked.connect(self.toggle_loop)
        self.fileTreeView.doubleClicked.connect(self.onFileTreeDoubleClicked)
        if self.mediaPlayer:
            self.volumeSlider.valueChanged.connect(self.mediaPlayer.set_volume)
        self.positionSlider.sliderPressed.connect(lambda: self.allow_position_updates(allow=False))
        self.positionSlider.sliderReleased.connect(lambda: (self.seek(self.positionSlider.value()), self.allow_position_updates(allow=True)))

    def allow_position_updates(self, allow: bool = True):
        self.update_slider = allow

    def open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Open Folder with Audio Files")
        if folder:
            self.fileDock.show()
            self.fileModel.setRootPath(folder)
            self.fileModel.sort(0, Qt.AscendingOrder)
            self.fileTreeView.setRootIndex(self.fileModel.index(folder))
            self.statusBar().showMessage(f"Opened folder: {folder}", 3000)
            self.folderAudioFiles.clear()
            self.trackMetadata.clear()
            audio_extensions = ('.mp3', '.wav', '.ogg', '.flac')
            all_files = os.listdir(folder)
            audio_files = [f for f in all_files if f.lower().endswith(audio_extensions)]
            files_with_path = [os.path.join(folder, f) for f in audio_files]
            all_have_track = True
            track_info = {}
            for full_path in files_with_path:
                meta = self.extractMetadata(full_path)
                track = meta.get('track')
                if track is None or track == "":
                    all_have_track = False
                    break
                try:
                    track_num = int(track)
                except ValueError:
                    all_have_track = False
                    break
                track_info[full_path] = track_num
            if all_have_track:
                sorted_files = sorted(files_with_path, key=lambda fp: track_info[fp])
            else:
                sorted_files = sorted(files_with_path)
            self.folderAudioFiles = sorted_files
            if self.folderAudioFiles and self.mediaPlayer:
                self.current_index = 0
                self.mediaPlayer.set_media(self.folderAudioFiles[0])
                self.updateTrackInfo()
            else:
                if self.mediaPlayer:
                    self.mediaPlayer.stop()
                self.playButton.setIcon(self.play_icon)
                self.resetTrackInfo()

    def onFileTreeDoubleClicked(self, index: QModelIndex):
        file_path = self.fileModel.filePath(index)
        if os.path.isfile(file_path) and file_path.lower().endswith(('.mp3', '.wav', '.ogg', '.flac')):
            try:
                idx = self.folderAudioFiles.index(file_path)
            except ValueError:
                idx = len(self.folderAudioFiles)
                self.folderAudioFiles.append(file_path)
            self.current_index = idx
            if self.mediaPlayer:
                self.mediaPlayer.set_media(file_path)
                self.mediaPlayer.play()
            self.playButton.setIcon(self.pause_icon)
            meta = self.extractMetadata(file_path)
            self.trackMetadata[idx] = meta
        self.updateTrackInfo()

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Audio File", "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac)"
        )
        if file_path:
            self.folderAudioFiles = [file_path]
            self.current_index = 0
            self.mediaPlayer.set_media(file_path)
            self.mediaPlayer.play()
            self.playButton.setIcon(self.pause_icon)
            self.updateTrackInfo()

    def play_pause(self):
        if self.mediaPlayer:
            if self.mediaPlayer.is_playing():
                self.mediaPlayer.pause()
                self.playButton.setIcon(self.play_icon)
            else:
                self.mediaPlayer.play()
                self.playButton.setIcon(self.pause_icon)

    def next_track(self):
        if self.folderAudioFiles and self.mediaPlayer:
            self.current_index = (self.current_index + 1) % len(self.folderAudioFiles)
            next_file = self.folderAudioFiles[self.current_index]
            self.mediaPlayer.set_media(next_file)
            self.mediaPlayer.play()
            self.playButton.setIcon(self.pause_icon)
            self.updateTrackInfo()

    def previous_track(self):
        if self.folderAudioFiles and self.mediaPlayer:
            self.current_index = (self.current_index - 1) % len(self.folderAudioFiles)
            prev_file = self.folderAudioFiles[self.current_index]
            self.mediaPlayer.set_media(prev_file)
            self.mediaPlayer.play()
            self.playButton.setIcon(self.pause_icon)
            self.updateTrackInfo()

    def toggle_shuffle(self):
        self.shuffle = not self.shuffle
        self.updatePlaybackMode()

    def toggle_loop(self):
        self.loop_mode = (self.loop_mode + 1) % 3
        self.updatePlaybackMode()

    def updatePlaybackMode(self):
        if self.shuffle:
            self.shuffleButton.setText("On")
        else:
            self.shuffleButton.setText("Off")
        loop_text = {0: "Off", 1: "All", 2: "One"}[self.loop_mode]
        self.loopButton.setText(loop_text)

    def on_position_changed(self, position):
        if self.update_slider:
            self.positionSlider.setValue(position)
            if self.mediaPlayer:
                self.update_time_labels(position, self.mediaPlayer.get_duration())

    def on_duration_changed(self, duration):
        self.positionSlider.setRange(0, duration)
        if self.mediaPlayer:
            self.update_time_labels(self.mediaPlayer.get_position(), duration)

    def update_position(self):
        if self.mediaPlayer:
            pos = self.mediaPlayer.get_position()
            if self.update_slider:
                self.positionSlider.setValue(pos)
            self.update_time_labels(pos, self.mediaPlayer.get_duration())
        self.update_status_bar()

    def update_time_labels(self, position, duration):
        def ms_to_minsec(ms):
            s = ms // 1000
            m = s // 60
            s = s % 60
            return f"{m}:{s:02d}"
        self.timeElapsedLabel.setText(ms_to_minsec(position))
        if duration > 0:
            self.timeRemainingLabel.setText(ms_to_minsec(duration))
        else:
            self.timeRemainingLabel.setText("0:00")

    def seek(self, position):
        if self.mediaPlayer:
            self.mediaPlayer.set_position(position)

    def update_status_bar(self):
        if not self.folderAudioFiles:
            self.statusBar().showMessage("Select a song to begin")
            return
        file_path = self.folderAudioFiles[self.current_index] if self.current_index < len(self.folderAudioFiles) else ""
        meta = self.trackMetadata.get(self.current_index, {})
        title = meta.get('title') or (os.path.basename(file_path) if file_path else "Unknown")
        artist = meta.get('artist') or "Unknown Artist"
        album = meta.get('album') or "Unknown Album"
        def ms_to_minsec(ms):
            s = ms // 1000
            m = s // 60
            s = s % 60
            return f"{m}:{s:02d}"
        duration = self.mediaPlayer.get_duration() if self.mediaPlayer else 0
        duration_str = ms_to_minsec(duration) if duration > 0 else "0:00"
        position = self.mediaPlayer.get_position() if self.mediaPlayer else 0
        position_str = ms_to_minsec(position)
        loop_text = {0: "Loop: Off", 1: "Loop: All", 2: "Loop: One"}[self.loop_mode]
        shuffle_text = "Shuffle: On" if self.shuffle else "Shuffle: Off"
        message = (
            f"Now Playing: {title} - {artist} | Album: {album} | "
            f"Duration: {duration_str} | Position: {position_str} | {loop_text} | {shuffle_text}"
        )
        self.statusBar().showMessage(message)



""" Start the program """
if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MusicPlayer()
    player.show()
    sys.exit(app.exec_())
