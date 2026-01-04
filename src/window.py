# window.py
#
# Copyright 2026 Golodnikov Sergey
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later


from gettext import gettext as _
from gi.repository import Adw, Gtk


@Gtk.Template(resource_path='/tech/digiroad/ImageFlow/gtk/window.ui')
class WindowIF(Adw.ApplicationWindow):
    __gtype_name__ = 'ImageFlow'

    title = Gtk.Template.Child('title')
    overlay = Gtk.Template.Child('overlay')

    open_file = Gtk.Template.Child('open-file')
    save_file = Gtk.Template.Child('save-file')

    generate = Gtk.Template.Child('generate')
    preview = Gtk.Template.Child('preview')

    image_size = Gtk.Template.Child('image-size')
    image_width = Gtk.Template.Child('image-width')
    image_height = Gtk.Template.Child('image-height')

    scaler = Gtk.Template.Child('scaler')
    keep_aspect_ratio = Gtk.Template.Child('keep-aspect-ratio')
    framerate = Gtk.Template.Child('framerate')

    palette = Gtk.Template.Child('palette')
    dither = Gtk.Template.Child('dither')
    format = Gtk.Template.Child('format')

    display = Gtk.Template.Child('display')
    loop = Gtk.Template.Child('loop')

    pref_dialog = Gtk.Template.Child('pref-dialog')

    pref_theme = Gtk.Template.Child('pref-theme')
    bayer_scale = Gtk.Template.Child('bayer-scale')
    accurate_rnd = Gtk.Template.Child('accurate-rnd')

    # variables for translation
    ts_save = _('Saved:')
    ts_size = _('Done, image size in MB:')
    ts_src = _('Source')
    ts_comment = _('Application for converting video files into '
                   'high-quality animated images.')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
