# data.py
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


from gettext import gettext as _
import re


# image size
size = (
    'Оriginal',
    (7680, 4320),
    (3840, 2160),
    (2560, 1440),
    (1920, 1080),
    (1280, 720),
    (640, 480),
    (480, 360),
    'User',
)

# interpolation method
scaler = (
    'area',
    'bicubic',
    'bicublin',
    'bilinear',
    'fast_bilinear',
    'gauss',
    'lanczos',
    'neighbor',
    'sinc',
    'spline',
)

# statistics mode
palette = (
    'diff',
    'full',
    'single',
)

# dithering mode
dither = (
    'atkinson',
    'bayer',
    'burkes',
    'floyd_steinberg',
    'heckbert',
    'none',
    'sierra2',
    'sierra2_4a',
    'sierra3',
)

# output file
format = (
    '.gif',
    '.webp',
)

webp_presets = (
    'none',
    'default',
    'picture',
    'photo',
    'drawing',
    'icon',
    'text',
)

# ------------------------------------------------------------------------------

timestamp_help = _(
    'Select «Start» or «End» and rewind the video to the desired frame, '
    'or enter the time in the corresponding field.'
)

time_format_options = {
    'h': (
        '00:00:00.000',
        re.compile(r'^([01]\d|2[0-3]):([0-5]\d):([0-5]\d)\.(\d{1,3})$'),
        _('Time format - hours:minutes:seconds.milliseconds (00:00:00.000)'),
    ),
    'm': (
        '00:00.000',
        re.compile(r'^([0-5]\d):([0-5]\d)\.(\d{1,3})$'),
        _('Time format - minutes:seconds.milliseconds (00:00.000)'),
    ),
    's': (
        '00.000',
        re.compile(r'^([0-5]\d)\.(\d{1,3})$'),
        _('Time format - seconds.milliseconds (00.000)'),
    ),
}
