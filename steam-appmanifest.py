#!/usr/bin/env python3

""" Steam AppManifest - Helper
Allows you to trick steam to download games on unsupported platforms.
Generates appmanifest_APPID.acf files in ~/.steam/steam/SteamApps
"""

import os
import sys
import time
import re
import json
import requests
from bs4 import BeautifulSoup

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402


class SteamAppNotFound(Exception):
    pass


class DlgToggleApp(Gtk.Dialog):
    def __init__(self, parent, exists, appid, name):
        print('[INFO] DlgToggleApp.__init__')
        Gtk.Dialog.__init__(self, "Install appmanifest", parent, 0)
        self.set_default_size(300, 100)

        label0 = Gtk.Label(label='Install "' + name + '"?')
        label1 = Gtk.Label(label="appmanifest_" + str(appid) + ".acf")

        if exists:
            self.set_title("appmanifest already exists")
            self.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "Delete anyway", Gtk.ResponseType.OK
            )
            label0.set_text("This will just remove the appmanifest file")
            label1.set_text('Use Steam to remove all of "' + name + '".')
        else:
            self.add_buttons(
                Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                "Install", Gtk.ResponseType.OK,
            )

        self.get_content_area().add(label0)
        self.get_content_area().add(label1)
        self.show_all()


class DlgManual(Gtk.Dialog):
    def __init__(self, parent):
        print('[INFO] DlgManual.__init__')
        Gtk.Dialog.__init__(
            self, title="Manually install appmanifest", parent=parent, flags=0
        )

        self.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OK, Gtk.ResponseType.OK
        )

        self.set_default_size(200, 50)

        appidlabel = Gtk.Label(label="Game AppID:")
        self.appidentry = Gtk.Entry()

        appidhbox = Gtk.HBox()
        appidhbox.pack_start(appidlabel, False, False, True)
        appidhbox.pack_start(self.appidentry, False, False, True)

        instdirlabel = Gtk.Label(label="Game directory name:")
        self.instdirentry = Gtk.Entry()

        instdirhbox = Gtk.HBox()
        instdirhbox.pack_start(instdirlabel, False, False, True)
        instdirhbox.pack_start(self.instdirentry, False, False, True)

        vbox = Gtk.VBox()
        vbox.pack_start(appidhbox, False, False, True)
        vbox.pack_start(instdirhbox, False, False, True)

        self.get_content_area().add(vbox)
        print("[INFO] Showing manual dialog (Done initializing)")
        self.show_all()


class AppManifest(Gtk.Window):
    # pylint: disable=too-many-locals,unused-argument
    def __init__(self, steamapps_path):
        print('[INFO] AppManifest.__init__')
        Gtk.Window.__init__(self, title="appmanifest.acf Generator")

        if not os.path.exists(steamapps_path):
            dialog = Gtk.MessageDialog(
                self,
                0,
                Gtk.MessageType.ERROR,
                Gtk.ButtonsType.OK,
                "Couldn't find a Steam install",
            )
            dialog.format_secondary_text('Looked in "' + steamapps_path + '"')
            dialog.run()
            dialog.destroy()
            sys.exit(1)

        self.set_default_size(480, 300)
        self.steampath = steamapps_path
        self.game_liststore = Gtk.ListStore(bool, int, str)
        self.main_gamelist_view = row2_treeview = Gtk.TreeView(model=self.game_liststore)  # noqa: E501

        row2 = Gtk.ScrolledWindow()
        row2_renderer_text = Gtk.CellRendererText()
        row2_renderer_check = Gtk.CellRendererToggle()
        row2_col_toggle = Gtk.TreeViewColumn("☑", row2_renderer_check, active=0)
        row2_col_appid = Gtk.TreeViewColumn("AppID", row2_renderer_text, text=1)  # noqa: E501
        row2_col_title = Gtk.TreeViewColumn("Title", row2_renderer_text, text=2)  # noqa: E501
        row2_renderer_check.connect("toggled", self.on_app_toggle)
        row2_treeview.append_column(row2_col_toggle)
        row2_treeview.append_column(row2_col_appid)
        row2_treeview.append_column(row2_col_title)
        row2.set_size_request(200, 400)
        row2.add(row2_treeview)

        row3 = Gtk.Box()
        row3_refresh = Gtk.Button(label="Refresh")
        row3_clear = Gtk.Button(label="Clear")
        row3_manual = Gtk.Button(label="Add")
        row3_quit = Gtk.Button(label="Quit")
        row3_refresh.connect("clicked", self.on_refresh_click)
        row3_clear.connect("clicked", self.on_clear_click)
        row3_manual.connect("clicked", self.on_manual_click)
        row3_quit.connect("clicked", self.on_quit_click)
        row3.pack_start(row3_refresh, True, True, 0)
        row3.pack_start(row3_clear, True, True, 0)
        row3.pack_start(row3_manual, True, True, 0)
        row3.pack_start(row3_quit, True, True, 0)

        notes_holder = Gtk.Label(
            label="\nRestart Steam for the changes to take effect." +
                  "\n\n------------------------------------------------------------\n"  # noqa: E501
        )

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        # vbox.pack_start(row0, False, False, True)
        vbox.pack_start(row2, True, True, 0)
        vbox.pack_start(row3, False, False, 0)
        vbox.pack_start(notes_holder, False, False, 0)

        self.add(vbox)
        print('[INFO] Done')

    def _exists(self, appid) -> bool:
        manifest_path = f"{self.steampath}/appmanifest_{appid}.acf"
        return os.path.isfile(manifest_path)

    @staticmethod
    def _get_app_name_from_steam(appid) -> dict:
        steam_community_page_url = f"https://steamcommunity.com/app/{appid}"
        steam_community_page_req = requests.get(steam_community_page_url)
        if steam_community_page_req.status_code != 200:
            raise SteamAppNotFound("invalid appid")

        steam_community_page_html = steam_community_page_req.text
        steam_community_page_soup = BeautifulSoup(
            steam_community_page_html, "html.parser"
        )
        config_divs = list(
            steam_community_page_soup.find_all("div", {"id": "application_config"})  # noqa: E501
        )

        if len(config_divs) != 1:
            raise SteamAppNotFound("config not found on page")

        config_div = config_divs[0]

        if "data-community" not in list(config_div.attrs.keys()):
            raise SteamAppNotFound("community config not found on page")

        community_data = json.loads(config_div.attrs["data-community"])

        return community_data["APP_NAME"]

    def reload_apps(self):
        print(f'[INFO] Scanning for files in: "{self.steampath}"...')

        self.game_liststore.clear()
        
        for file in os.listdir(self.steampath):
            file_path = os.path.join(self.steampath, file)
            exists = os.path.isfile(file_path)

            matches = re.search(r"appmanifest_([0-9]+).acf", file)
            if not matches:
                continue

            appid = int(matches.groups(1)[0])

            print(f"[INFO]   - Found: {file_path} * ({appid})")

            # appids.append(appid)
            # files.append(file_path)
            game_name = AppManifest._get_app_name_from_steam(appid)
            self.game_liststore.append([exists, appid, game_name])

    def on_refresh_click(self, widget):
        print("[INFO] Refresh all apps")
        self.reload_apps()
        print('[INFO] Done')

    def on_app_toggle(self, widget, path):
        name = self.game_liststore[path][2]
        appid = self.game_liststore[path][1]
        exists = self.refresh_single_row(path)
        manifest_path = f"{self.steampath}/appmanifest_{appid}.acf"

        if exists:
            action_msg = "Removing"
            def action_func(): os.remove(manifest_path)
        else:
            action_msg = "Adding"
            def action_func(): self.add_game(appid, name)

        def cancel_func(): print(f"[INFO] {action_msg} cancelled")

        print(f"{action_msg} app")

        dialog = DlgToggleApp(self, exists, appid, name)

        if dialog.run() == Gtk.ResponseType.OK:
            action_func()
        else:
            cancel_func()
        dialog.destroy()

        self.refresh_single_row(path)

    def on_manual_click(self, widget):
        print("[INFO] Add game (manual)")
        dialog = DlgManual(self)
        response = dialog.run()

        if response == Gtk.ResponseType.OK:
            self.add_game(
                int(dialog.appidentry.get_text()), dialog.instdirentry.get_text()  # noqa: E501
            )

        dialog.destroy()
        print('[INFO] Done')

    def on_quit_click(self, widget):
        print("[DEBUG] Emitting event: destroy")
        # time.sleep(5)
        self.emit("destroy")
        # self.destroy()
        # Gtk.main_quit()
        print('[INFO] Done')

    def on_clear_click(self, widget):
        print('[INFO] Clear files')

        self.game_liststore.clear()
        print('[INFO] Done')

    def refresh_single(self, appid):
        print("[INFO] Refresh single app")
        exists = self._exists(appid)

        for row in self.game_liststore:
            if row[1] == appid:
                row[0] = exists
                break

        print('[INFO] Done')
        return exists

    def refresh_single_row(self, row):
        appid = self.game_liststore[row][1]
        exists = self._exists(appid)

        self.game_liststore[row][0] = exists

        return exists

    def add_game(self, appid, name):
        manifest_path = f"{self.steampath}/appmanifest_{appid}.acf"
        print(f'[INFO] Adding manifest for game {name}: "{manifest_path}"')

        install_dir = name.replace('/', '').replace(' ', '')
        name = name.replace("/", "-")
        with open(manifest_path, "w") as file_handle:
            file_handle.write((
                '"AppState"\n'
                '{\n'
                f'    "appid"        "{appid}"\n'
                '    "Universe"      "1"\n'
                f'    "name"         "{name}"\n'
                f'    "installdir"   "{install_dir}"\n'
                '    "StateFlags"    "4"\n'
                '    "UserConfig"\n'
                '    {\n'
                '        "language"        "english"\n'
                '    }\n'
                "}"
            ))
        print('[INFO] Done')


def main():
    print("[DEBUG] main")
    steamapps_path = os.path.expanduser("~/Library/Application Support/Steam/steamapps")  # noqa: E501

    print(f"[DEBUG] SteamApps path: {steamapps_path}")

    win = AppManifest(steamapps_path)
    win.connect("destroy", Gtk.main_quit)
    win.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
