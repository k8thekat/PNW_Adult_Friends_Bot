from __future__ import annotations

__title__ = "MrFriendly Bot"
__author__ = "k8thekat"
__license__ = "GNU"
__version__ = "0.0.1"
__credits__ = "k8thekat and LightningTH"

from typing import Literal, NamedTuple


class VersionInfo(NamedTuple):
    Major: int
    Minor: int
    Revision: int
    releaseLevel: Literal["alpha", "beta", "pre-release", "release", "development"]


version_info: VersionInfo = VersionInfo(Major=0, Minor=0, Revision=1, releaseLevel="release")

del NamedTuple, Literal, VersionInfo
