# Copyright 2026 MIT
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


"""Shared Xbox controller /joy index mapping loader for UAV Neo.

Single source of truth: ``config/xbox_mapping.yaml`` (installed to the package
share). Both the ROS2 ``mux_node`` and the student library ``ControllerReal``
load the mapping through here, so the button/axis -> /joy array indices live in
exactly one file and can be re-mapped for a different controller without a code
change.
"""

import os

from ament_index_python.packages import get_package_share_directory
import yaml

# Fallback = the empirically-verified mapping for the kit's ESM-9110 controller
# in its standardized XInput mode (8 axes / 11 buttons, standard xpad layout),
# determined by manual testing 2026-07-05. Used only when the YAML is missing or
# a key is absent, so a bad/partial config can never crash the safety-relevant
# mux; it degrades to these known-good values instead.
DEFAULT_MAPPING = {
    'report': {'buttons': 11, 'axes': 8},
    'buttons': {
        'a': 0, 'b': 1, 'x': 2, 'y': 3,
        'lb': 4, 'rb': 5, 'back': 6, 'start': 7, 'guide': 8,
        'left_stick': 9, 'right_stick': 10,
    },
    'axes': {
        'left_x': 0, 'left_y': 1, 'left_trigger': 2,
        'right_x': 3, 'right_y': 4, 'right_trigger': 5,
        'dpad_x': 6, 'dpad_y': 7,
    },
}


def default_mapping_path():
    """Absolute path to the installed ``xbox_mapping.yaml`` ('' if unresolved)."""
    try:
        share = get_package_share_directory('uav_neo_ros2_driver')
    except Exception:
        return ''
    return os.path.join(share, 'config', 'xbox_mapping.yaml')


def load_mapping(path=None):
    """Load the controller mapping, overlaying the YAML onto ``DEFAULT_MAPPING``.

    Args:
        path: Path to the mapping YAML. Defaults to the installed
            ``config/xbox_mapping.yaml``.

    Returns:
        ``{'buttons': {name: index, ...}, 'axes': {name: index, ...}}``.

    A missing file or missing keys silently fall back to the built-in defaults;
    only a syntactically broken YAML propagates its parse error.
    """
    if path is None:
        path = default_mapping_path()

    merged = {group: dict(entries) for group, entries in DEFAULT_MAPPING.items()}
    if path and os.path.isfile(path):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        for group in merged:
            if isinstance(data.get(group), dict):
                merged[group].update(data[group])
    return merged
