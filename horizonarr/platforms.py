"""IGDB platform ids, the filter groups shown on the page and the names used on cards."""

NAMES = {
    6: "PC", 14: "Mac", 3: "Linux", 130: "Switch", 508: "Switch 2", 48: "PS4", 167: "PS5", 49: "Xbox One",
    169: "Xbox Series", 9: "PS3", 12: "Xbox 360", 41: "Wii U", 5: "Wii", 21: "GameCube", 8: "PS2", 11: "Xbox",
    38: "PSP", 46: "PS Vita", 37: "3DS", 20: "DS", 18: "NES", 19: "SNES", 4: "N64", 33: "Game Boy",
    22: "GBC", 24: "GBA", 7: "PS1", 29: "Mega Drive", 64: "Master System", 35: "Game Gear", 32: "Saturn",
    23: "Dreamcast", 78: "Sega CD", 30: "32X", 59: "Atari 2600", 60: "Atari 7800", 61: "Atari Lynx",
    62: "Jaguar", 16: "Amiga", 15: "C64", 26: "ZX Spectrum", 25: "Amstrad CPC", 27: "MSX", 13: "DOS",
    52: "Arcade", 86: "PC Engine", 80: "Neo Geo", 119: "Neo Geo Pocket", 57: "WonderSwan", 87: "Virtual Boy",
    58: "Super Famicom", 99: "Famicom", 51: "Famicom Disk", 306: "Satellaview", 137: "New 3DS", 159: "DSi",
    34: "Android", 39: "iOS", 170: "Stadia", 165: "PS VR", 390: "PS VR2", 384: "Oculus Quest", 471: "Meta Quest 3",
    386: "Meta Quest 2", 162: "Oculus VR", 163: "SteamVR", 72: "Ouya", 82: "Web", 47: "Virtual Console", 132: "Amazon Fire TV",
    128: "PC Engine CD", 150: "Turbografx-16 CD", 136: "Neo Geo CD", 50: "3DO", 117: "CD-i", 66: "Atari 5200",
    63: "Atari ST", 65: "Atari 8-bit", 75: "Apple II",
}
# Hidden on cards: IGDB has dozens of niche ids; unknown ones are left out rather than shown as numbers


GROUPS = {
    "PC": [6], "Mac": [14], "Switch": [130], "Switch 2": [508], "PlayStation": [48, 167], "Xbox": [49, 169],
    "Retro": [18, 19, 29, 24, 33, 22, 4, 7, 23, 16, 64, 32, 35, 59],
}
MODERN = [p for g in ("PC", "Mac", "Switch", "Switch 2", "PlayStation", "Xbox") for p in GROUPS[g]]

# Systems offered in Explore, grouped for the picker
EXPLORE = {
    "Atuais": [6, 14, 508, 130, 167, 48, 169, 49],
    "Geração anterior": [9, 12, 41, 5, 21, 8, 11, 38, 46, 37, 20],
    "Retro Nintendo": [18, 19, 4, 33, 22, 24, 87],
    "Retro Sega": [64, 29, 78, 30, 32, 23, 35],
    "Retro Sony/Atari/outros": [7, 59, 60, 61, 62, 86, 80, 119, 57, 52],
    "Computadores": [16, 15, 26, 25, 27, 13],
}

# When a game is on several systems, the RetroArr entry goes to the first one in this order
ADD_PRIORITY = [6, 508, 130, 167, 48, 169, 49, 14, 9, 12, 41, 5, 21, 8, 11, 38, 46, 37, 20, 18, 19, 4, 33, 22,
                24, 7, 29, 64, 35, 32, 23, 78, 30, 59, 60, 61, 62, 16, 15, 26, 25, 27, 13, 52, 86, 80, 119, 57, 87]

# Prowlarr/Newznab categories: 4000 = PC, 1000 = console
PC_LIKE = {6, 14, 3, 13}


def name(pid):
    return NAMES.get(pid, f"#{pid}")


def known(pids):
    """Only the platforms we have a name for, in the given order."""
    return [p for p in pids if NAMES.get(p)]


def search_categories(platforms):
    return "4000" if set(platforms) & PC_LIKE else "1000"


def pick_for_add(platforms):
    """The platform a new RetroArr entry should use, or None if none of them is known."""
    return next((p for p in ADD_PRIORITY if p in platforms), platforms[0] if platforms else None)
