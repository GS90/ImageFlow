# main.py
#
# Copyright 2026 Golodnikov Sergey
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty
# of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later


from datetime import timedelta
import os
import re
import shutil
import subprocess
import sys
import threading
import webbrowser

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import data
from .window import WindowIF


APP_VERSION = '1.1.0'

TMP_NAME = 'result'


class ImageFlowApplication(Adw.Application):
    def __init__(self):
        super().__init__(application_id='tech.digiroad.ImageFlow',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/tech/digiroad/ImageFlow')
        self.create_action('open', self.open_file, ['<primary>o'])
        self.create_action('about', self.about_action, None)
        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('preferences',
                           self.preferences_action,
                           ['<primary>p'])

    def do_activate(self):
        self.settings = Gio.Settings.new('tech.digiroad.ImageFlow')

        self.options = {}
        self.options_exceptions = (
            'theme',
            'detect-size',
            'loop',
            'accurate-rnd',
            'stats-mode',
            'bayer-scale',
            'webp-lossless',
            'webp-quality',
            'webp-preset',
        )
        self.options_load()

        self.w = self.props.active_window
        if not self.w:
            self.w = WindowIF(application=self)
        self.w.present()

        self.update_theme(self.settings.get_int('theme'))

        loop_state = self.settings.get_boolean('loop')
        self.w.loop.set_active(loop_state)
        self.w.video.set_loop(loop_state)

        self.options_set()

        self.source, self.result, self.current = '', '', ''

        self.name, self.file_format = '', ''

        self.dir = GLib.get_user_cache_dir()
        self.palette = os.path.join(self.dir, 'palette.png')
        self.sources_size = None

        self.stream = None
        self.enable_trim = False
        self.segment_point = 0  # 1:start, 2:end
        self.segment_format = 'h'
        self.segment_format_options = data.time_format_options['h']
        self.segment_value_start = 0
        self.segment_value_end = 0

        self.freeze = False

        self.w.pref_theme.connect('notify::selected-item', self.theme_change)

        self.w.external.connect('clicked', self.browser_preview)
        self.w.generate.connect('activated', self.generate_wrapper)
        self.w.image_height.connect('notify::value', self.size_change)
        self.w.image_size.connect('notify::selected-item', self.size_switch)
        self.w.image_width.connect('notify::value', self.size_change)
        self.w.keep_aspect_ratio.connect('notify::active', self.ratio_state)
        self.w.loop.connect('toggled', self.loop_state)
        self.w.open_file.connect('clicked', self.open_file)
        self.w.preview.connect('notify::active', self.preview_switch)
        self.w.save_file.connect('activated', self.save_file)
        self.w.trim.connect('toggled', self.trim_state)

        # trim, segment
        self.w.segment_button_start.connect(
            'clicked', self.segment_button_start)
        self.w.segment_button_end.connect(
            'clicked', self.segment_button_end)
        self.w.segment_entry_start.connect(
            'activate', self.segment_entry_start)
        self.w.segment_entry_end.connect(
            'activate', self.segment_entry_end)
        # format check
        self.w.format.connect('notify::selected-item', self.format_switch)
        self.format_switch(self.w.format, None)
        # drag and drop
        drop_target = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop_target.connect('drop', self.on_drop)
        self.w.display.add_controller(drop_target)

    # --------------------------------------------------------------------------

    def switch_control(self, generate: bool, preview: bool, save: bool):
        # generate
        self.w.generate.set_sensitive(generate)
        if generate:
            self.w.generate.add_css_class('warning')
        else:
            self.w.generate.remove_css_class('warning')
        # preview
        self.w.preview.set_sensitive(preview)
        if preview:
            self.w.preview.add_css_class('success')
        else:
            self.w.preview.remove_css_class('success')
        self.w.preview.set_active(preview)
        # save
        self.w.save_file.set_sensitive(save)
        if save:
            self.w.save_file.add_css_class('suggested-action')
        else:
            self.w.save_file.remove_css_class('suggested-action')

    # --------------------------------------------------------------------------

    def accept_file(self, path: str):
        self.result, self.name = '', ''
        self.source = path
        self.w.video.set_filename(self.source)
        self.current = self.source
        self.w.open_file.remove_css_class('suggested-action')
        self.w.title.set_subtitle(os.path.basename(self.source))
        self.switch_control(generate=True, preview=False, save=False)
        self.file_parsing()
        # stream & trim
        self.stream = self.w.video.get_media_stream()
        self.stream.connect("notify::timestamp", self.get_timestamp)
        self.trim_access(True)

    def on_drop(self, _drop, value, _x, _y):
        if not value:
            return False
        path = value.get_path()
        if not os.path.exists(path):
            self.message_show(*self.w.ts_error_permissions)
            return False
        else:
            self.accept_file(path)
            return True

    def file_parsing(self):
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-select_streams', 'v',
            '-show_entries', 'stream=width,height',
            '-show_entries', 'format=duration',
            '-of', 'csv=p=0', self.source
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err = result.stderr.decode('utf-8').strip()
            self.message_show('Analysis error', err)
            return
        lines = result.stdout.decode('utf-8').strip().split('\n')
        if len(lines) < 2:
            return
        size, duration = lines[0], lines[1]
        # duration
        try:
            duration = int(float(duration) * 1000000)
            self.segment_range_set(duration, init=True)
        except ValueError as err:
            self.message_show('Analysis error', str(err))
        # size
        split = size.split(',')
        if len(split) == 2:
            try:
                width, height = int(split[0]), int(split[1])
                self.sources_size = (width, height)
                if self.settings.get_boolean('detect-size'):
                    self.freeze = True
                    self.w.image_width.set_value(width)
                    self.w.image_height.set_value(height)
                    self.freeze = False
                    self.w.image_size.set_selected(0)
            except ValueError as err:
                self.message_show('Analysis error', str(err))

    # --------------------------------------------------------------------------

    def open_file(self, _button, _=None):
        dialog = Gtk.FileChooserNative.new(
            title='Select a video file',
            parent=self.w.get_native(),
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.set_modal(True)

        # all files:
        filter = Gtk.FileFilter.new()
        filter.set_name('All')
        filter.add_pattern('*.*')
        dialog.add_filter(filter)

        # video files:
        filter = Gtk.FileFilter.new()
        filter.set_name('Video')

        types = (
            'video/mp4',
            'video/mpeg',
            'video/ogg',
            'video/quicktime',
            'video/webm',
            'video/x-matroska',
        )
        for t in types:
            filter.add_mime_type(t)

        extensions = (
            '*.avi',
            '*.mkv',
            '*.mov',
            '*.mp4',
            '*.mpeg',
            '*.mpg',
            '*.webm',
        )
        for e in extensions:
            filter.add_pattern(e)

        dialog.add_filter(filter)
        dialog.set_filter(filter)

        def open_file_response(dialog, response_id):
            if response_id == Gtk.ResponseType.ACCEPT:
                file = dialog.get_file()
                if file:
                    self.accept_file(file.get_path())
            dialog.destroy()

        dialog.connect('response', open_file_response)
        dialog.show()

    def save_file(self, _):
        def save_file_finish(dialog, result):
            try:
                file = dialog.save_finish(result)
                if file:
                    fp = file.get_path()
                    shutil.copy2(self.result, fp)
                    toast_title = f'{self.w.ts_save} {self.name}'
                    toast = Adw.Toast.new(title=toast_title)
                    toast.set_button_label(button_label=self.w.ts_save_show)
                    toast.connect('button-clicked',
                                  lambda s: self.toast_button_show(s, fp))
                    self.w.overlay.add_toast(toast)
            except Exception as err:
                err = str(err)
                if 'dismissed by user' not in err.lower():
                    self.message_show('Saving error', err)

        dialog = Gtk.FileDialog.new()
        dialog.set_title('Save result')
        dialog.set_initial_name(self.name)
        dialog.save(self.w, None, save_file_finish)

    # --------------------------------------------------------------------------

    def stack_adjust_visibility(self, obj: str):
        match obj:
            case 'display':
                self.w.display.set_visible(True)
                self.w.spinner.set_visible(False)
                self.w.external.set_visible(False)
            case 'spinner':
                self.w.display.set_visible(False)
                self.w.spinner.set_visible(True)
                self.w.external.set_visible(False)
            case 'external':
                self.w.display.set_visible(False)
                self.w.spinner.set_visible(False)
                self.w.external.set_visible(True)

    def format_switch(self, widget, _):
        self.file_format = data.format[widget.get_selected()]
        v = True if self.file_format == '.gif' else False
        self.w.max_colors.set_sensitive(v)
        self.w.dither.set_sensitive(v)

    def size_switch(self, widget, _):
        self.freeze = True
        size = data.size[widget.get_selected()]
        if size == 'Оriginal':
            if self.sources_size is not None:
                self.w.image_width.set_value(self.sources_size[0])
                self.w.image_height.set_value(self.sources_size[1])
        elif size == 'User':
            pass
        else:
            self.w.image_width.set_value(size[0])
            self.w.image_height.set_value(size[1])
        self.freeze = False

    def size_change(self, _widget, _):
        if not self.freeze:
            self.w.image_size.set_selected(len(data.size) - 1)

    def ratio_state(self, widget, _):
        state = widget.get_active()
        self.w.image_height.set_sensitive(False if state else True)

    def loop_state(self, toggle_button):
        state = toggle_button.get_active()
        self.settings.set_boolean('loop', state)
        self.w.video.set_loop(state)
        if self.current != '':
            self.w.video.set_filename(self.current)

    # --------------------------------------------------------------------------

    def trim_state(self, toggle_button):
        if self.freeze:
            return
        self.segment_point = 0
        if self.source == '':
            return
        if self.source != self.current:
            return
        state = toggle_button.get_active()
        self.enable_trim = state
        self.w.segment.set_visible(state)
        if state:
            duration = self.stream.get_duration()
            if duration != 0:
                self.segment_range_set(self.stream.get_duration())

    def trim_access(self, access: bool):
        self.freeze = True
        if access:
            self.w.trim.set_sensitive(True)
        else:
            self.segment_point = 0
            self.w.segment.set_visible(False)
            self.w.segment_box_start.remove_css_class('success')
            self.w.segment_box_end.remove_css_class('success')
            self.w.trim.set_active(False)
            self.w.trim.set_sensitive(False)
        self.freeze = False

    # --------------------------------------------------------------------------

    def get_timestamp(self, _f, _p):
        if self.segment_point != 0:
            self.segment_range_set(self.stream.get_timestamp())

    def segment_button_start(self, _, entry=False):
        self.enable_trim = True
        if self.segment_point == 1:  # start
            if entry:
                return
            self.segment_point = 0
            self.w.segment_box_start.remove_css_class('success')
        else:
            self.segment_point = 1
            self.w.segment_box_start.add_css_class('success')
            self.w.segment_box_end.remove_css_class('success')

    def segment_button_end(self, _, entry=False):
        self.enable_trim = True
        if self.segment_point == 2:  # end
            if entry:
                return
            self.segment_point = 0
            self.w.segment_box_end.remove_css_class('success')
        else:
            self.segment_point = 2
            self.w.segment_box_start.remove_css_class('success')
            self.w.segment_box_end.add_css_class('success')

    def segment_entry_start(self, entry):
        text = entry.get_text()
        if re.fullmatch(self.segment_format_options[1], text):
            entry.remove_css_class('error')
            microseconds = self.text_to_microseconds(text)
            self.stream.seek(microseconds)
            self.segment_value_start = microseconds
            self.segment_button_start(None, True)
        else:
            entry.add_css_class('error')

    def segment_entry_end(self, entry):
        text = entry.get_text()
        if re.fullmatch(self.segment_format_options[1], text):
            entry.remove_css_class('error')
            microseconds = self.text_to_microseconds(text)
            self.stream.seek(microseconds)
            self.segment_value_end = microseconds
            self.segment_button_end(None, True)
        else:
            entry.add_css_class('error')

    def segment_range_set(self, microseconds, init=False):
        delta = timedelta(microseconds=microseconds)
        total_seconds = delta.total_seconds()

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        seconds_str = f'{seconds:06.3f}'

        if init:
            if hours > 0:
                self.segment_format = 'h'
                self.segment_format_options = data.time_format_options['h']
            elif minutes > 0:
                self.segment_format = 'm'
                self.segment_format_options = data.time_format_options['m']
            else:
                self.segment_format = 's'
                self.segment_format_options = data.time_format_options['s']
            self.w.segment.set_tooltip_text(
                f'{self.segment_format_options[2]}\n\n{data.timestamp_help}'
            )

        match self.segment_format:
            case 'h': value = f'{hours:02d}:{minutes:02d}:{seconds_str}'
            case 'm': value = f'{minutes:02d}:{seconds_str}'
            case 's': value = seconds_str

        match self.segment_point:
            case 0:
                self.segment_value_start = 0
                self.segment_value_end = microseconds
                self.w.segment_entry_start.set_text(
                    self.segment_format_options[0])
                self.w.segment_entry_end.set_text(value)
            case 1:  # start
                if microseconds > self.segment_value_end:
                    return
                self.w.segment_entry_start.remove_css_class('error')
                self.segment_value_start = microseconds
                self.w.segment_entry_start.set_text(value)
            case 2:  # end
                if microseconds < self.segment_value_start:
                    return
                self.w.segment_entry_end.remove_css_class('error')
                self.segment_value_end = microseconds
                self.w.segment_entry_end.set_text(value)

    def segment_range_get(self):
        return [
            '-ss', self.microseconds_to_hms(self.segment_value_start),
            '-to', self.microseconds_to_hms(self.segment_value_end),
        ]

    def microseconds_to_hms(self, microseconds):
        delta = timedelta(microseconds=microseconds)
        total_seconds = int(delta.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = delta.microseconds // 1000
        return f'{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}'

    def text_to_microseconds(self, text: str):
        text = text.strip()

        parts = text.split(':')
        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            split = parts[2].split('.')
            seconds = int(split[0])
            milliseconds = int(split[1]) if len(split) > 1 else 0
        elif len(parts) == 2:
            hours = 0
            minutes = int(parts[0])
            split = parts[1].split('.')
            seconds = int(split[0])
            milliseconds = int(split[1]) if len(split) > 1 else 0
        elif len(parts) == 1:
            hours = 0
            minutes = 0
            split = parts[0].split('.')
            seconds = int(split[0])
            milliseconds = int(split[1]) if len(split) > 1 else 0
        else:
            err = f'Format parsing error: option "{text}" is invalid'
            self.message_show('Timestamp', err)
            return

        return (hours * 3600 + minutes * 60 + seconds) * 1000000 \
            + milliseconds * 1000

    # --------------------------------------------------------------------------

    def preview_switch(self, widget, _):
        if self.result != '':
            if widget.get_active():
                if self.file_format == '.webp':
                    self.stack_adjust_visibility('external')
                else:
                    self.w.video.set_filename(self.result)
                    self.stack_adjust_visibility('display')
                self.current = self.result
                self.w.preview.add_css_class('success')
                # trim
                self.trim_access(False)
            else:
                self.stack_adjust_visibility('display')
                self.w.video.set_filename(self.source)
                self.current = self.source
                self.w.preview.remove_css_class('success')
                # trim & stream
                self.trim_access(True)
                self.stream = self.w.video.get_media_stream()
                self.stream.connect("notify::timestamp", self.get_timestamp)

    def toast_button_show(self, _, fp: str):
        fd = os.path.dirname(fp)
        if os.path.isdir(fd):
            subprocess.run(['xdg-open', fd])

    def browser_preview(self, _):
        webbrowser.open(url=self.result, new=2)

    # --------------------------------------------------------------------------

    def options_load(self):
        for k in self.settings.keys():
            if k in self.options_exceptions:
                continue
            elif k == 'ratio':
                self.options[k] = self.settings.get_boolean(k)
            else:
                self.options[k] = self.settings.get_int(k)

    def options_save(self):
        self.options_get()
        for k in self.options:
            if k == 'ratio':
                self.settings.set_boolean(k, self.options[k])
            else:
                self.settings.set_int(k, self.options[k])

    def options_set(self):
        self.w.image_size.set_selected(self.options['image-size'])
        self.w.image_width.set_value(self.options['image-width'])
        self.w.image_height.set_value(self.options['image-height'])
        self.w.scaler.set_selected(self.options['scaler'])
        self.w.keep_aspect_ratio.set_active(self.options['ratio'])
        self.w.framerate.set_value(self.options['fps'])
        self.w.dither.set_selected(self.options['dither'])
        self.w.max_colors.set_value(self.options['max-colors'])
        self.w.format.set_selected(self.options['format'])
        self.ratio_state(self.w.keep_aspect_ratio, None)

    def options_get(self):
        self.options = {
            'image-width': int(self.w.image_width.get_value()),
            'image-height': int(self.w.image_height.get_value()),
            'scaler': self.w.scaler.get_selected(),
            'ratio': self.w.keep_aspect_ratio.get_active(),
            'fps': int(self.w.framerate.get_value()),
            'max-colors': self.w.max_colors.get_value(),
            'dither': self.w.dither.get_selected(),
            'format': self.w.format.get_selected(),
        }
        size = self.w.image_size.get_selected()
        if size != 0:  # 0 == original
            self.options['image-size'] = size

    # --------------------------------------------------------------------------

    def preparation(self):
        self.result = os.path.join(self.dir, TMP_NAME + self.file_format)

        width = self.options['image-width']
        height = self.options['image-height']

        if self.options['ratio']:
            scale = f"scale={width}:-1"
        else:
            scale = f'scale={width}:{height}'

        scaler = data.scaler[self.options['scaler']]
        if self.settings.get_boolean('accurate-rnd'):
            scaler += '+accurate_rnd'

        uno = f"fps={self.options['fps']},{scale}:flags={scaler}"

        if self.file_format == '.gif':
            # palette generation
            dither = data.dither[self.options['dither']]
            if dither == 'bayer':
                bs = self.settings.get_int('bayer-scale')
                dither += ':bayer_scale=' + str(bs)

            palette = data.palette[self.settings.get_int('stats-mode')]
            palette += f":max_colors={self.options['max-colors']}"

            dos = f"{uno},palettegen=stats_mode={palette}"
            tres = f"paletteuse=dither={dither}"
        else:
            dos, tres = None, None  # for palette only

        if self.file_format == '.webp':
            cuatro = [
                '-c:v', 'libwebp',
                '-lossless',
                '1' if self.settings.get_boolean('webp-lossless') else '0',
                '-q:v',
                str(self.settings.get_int('webp-quality')),
                '-preset',
                data.webp_presets[self.settings.get_int('webp-preset')],
                '-compression_level',
                str(self.settings.get_int('webp-compression')),
                '-loop', '0', '-vsync', '0', '-y',
            ]
        else:
            cuatro = ['-vsync', '0', '-y']

        return (uno, dos, tres, cuatro)

    def generate(self, uno, dos, tres, cuatro):
        if self.enable_trim:
            src = [*self.segment_range_get(), '-i', self.source]
        else:
            src = ['-i', self.source,]

        cmd = ['ffmpeg', '-v', 'error', *src, '-an']

        if self.file_format == '.gif':
            # palette
            result = subprocess.run([
                'ffmpeg', '-v', 'error', *src,
                '-vf', dos, '-y', self.palette,
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode != 0:
                err = result.stderr.decode('utf-8').strip()
                self.message_show('Palette error', err)
                self.result = ''
                return
            cmd.extend((
                '-i', self.palette,
                '-filter_complex', f'{uno} [x]; [x][1:v] {tres}',
                *cuatro, self.result,
            ))
        else:
            cmd.extend(('-vf', uno, *cuatro, self.result))

        # conversion
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err = result.stderr.decode('utf-8').strip()
            self.message_show('Generation error', err)
            self.result = ''
            return

        GLib.idle_add(self.generation_complete)

    def generation_complete(self):
        basename = os.path.splitext(os.path.basename(self.source))[0]
        self.name = basename + self.file_format

        file_size = round(os.path.getsize(self.result) / (1024 ** 2), 1)
        file_size = str(file_size).replace('.', ',')
        self.w.overlay.add_toast(Adw.Toast(
            title=f'{self.w.ts_size} {file_size}',
            timeout=4,
        ))

        self.w.video.set_filename(self.result)
        self.current = self.result
        self.switch_control(generate=True, preview=True, save=True)

    def generate_wrapper(self, _):
        self.switch_control(generate=False, preview=False, save=False)
        self.trim_access(False)
        self.stack_adjust_visibility('spinner')
        self.options_save()
        args = self.preparation()
        thread = threading.Thread(target=self.generate, args=args, daemon=True)
        thread.start()

    # --------------------------------------------------------------------------

    def about_action(self, *_args):
        about = Adw.AboutDialog(
            application_name='ImageFlow',
            application_icon='tech.digiroad.ImageFlow',
            developer_name='Golodnikov Sergey',
            version=APP_VERSION,
            comments=(self.w.ts_comment),
            website='https://digiroad.tech',
            developers=['Golodnikov Sergey <nn19051990@gmail.com>'],
            artists=[
                'Golodnikov Sergey <nn19051990@gmail.com>',
                'GNOME Design Team https://welcome.gnome.org/team/design',
            ],
            copyright='Copyright © 2026 Golodnikov Sergey',
            license_type=Gtk.License.GPL_3_0,
        )
        about.add_link((self.w.ts_src), 'https://github.com/GS90/ImageFlow')
        about.present(self.props.active_window)

    def preferences_action(self, _widget, _):
        self.w.pref_theme.set_selected(
            self.settings.get_int('theme'))
        self.w.detect_size.set_active(
            self.settings.get_boolean('detect-size'))
        self.w.accurate_rnd.set_active(
            self.settings.get_boolean('accurate-rnd'))
        self.w.stats_mode.set_selected(
            self.settings.get_int('stats-mode'))
        self.w.bayer_scale.set_value(
            self.settings.get_int('bayer-scale'))
        self.w.webp_lossless.set_active(
            self.settings.get_boolean('webp-lossless'))
        self.w.webp_quality.set_value(
            self.settings.get_int('webp-quality'))
        self.w.webp_preset.set_selected(
            self.settings.get_int('webp-preset'))
        self.w.webp_compression.set_value(
            self.settings.get_int('webp-compression'))
        self.w.pref_dialog.connect('closed', self.preferences_save)
        self.w.pref_dialog.present(self.props.active_window)

    def preferences_save(self, _):
        self.settings.set_int(
            'theme', self.w.pref_theme.get_selected())
        self.settings.set_boolean(
            'detect-size', self.w.detect_size.get_active())
        self.settings.set_boolean(
            'accurate-rnd', self.w.accurate_rnd.get_active())
        self.settings.set_int(
            'stats-mode', int(self.w.stats_mode.get_selected()))
        self.settings.set_int(
            'bayer-scale', int(self.w.bayer_scale.get_value()))
        self.settings.set_boolean(
            'webp-lossless', self.w.webp_lossless.get_active())
        self.settings.set_int(
            'webp-quality', int(self.w.webp_quality.get_value()))
        self.settings.set_int(
            'webp-preset', int(self.w.webp_preset.get_selected()))
        self.settings.set_int(
            'webp-compression', int(self.w.webp_compression.get_value()))

    def theme_change(self, widget, _):
        self.update_theme(widget.get_selected())

    def update_theme(self, value: int):
        style_manager = Adw.StyleManager.get_default()
        if value == 0:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT)
        else:
            style_manager.set_color_scheme(Adw.ColorScheme.FORCE_DARK)

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect('activate', callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f'app.{name}', shortcuts)

    def message_show(self, message: str, detail: str):
        dialog = Gtk.AlertDialog(
            message=message,
            detail=detail,
            buttons=('Cancel',),
        )
        dialog.choose(
            parent=self.w,
            cancellable=None,
            callback=None,
            user_data=None,
        )

    def do_shutdown(self):
        # deleting temporary files
        if self.palette != '' and os.path.exists(self.palette):
            os.remove(self.palette)
        for i in data.format:
            file = os.path.join(self.dir, TMP_NAME + i)
            if os.path.exists(file):
                os.remove(file)
        # shutdown
        Gio.Application.do_shutdown(self)


def main(version):
    app = ImageFlowApplication()
    return app.run(sys.argv)
