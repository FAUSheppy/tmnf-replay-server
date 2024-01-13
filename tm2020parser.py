import re
import os
import datetime
import hashlib
import pygbx
import xmltodict

def get_latest_season_from_maps(maps):
    '''Determine the latest season in DB'''

    order = ["Winter", "Spring", "Summer", "Fall"]

    max_year = 0
    max_season = "Winter"

    if not maps:
        return

    for m in maps:
        splitted = m.map_uid.split(" ")

        # not a campain map #
        if len(splitted) < 3:
            return

        season = splitted[0]
        year = splitted[1]

        # also not a campaing map #
        if not season in order:
            return
        try:
            year = int(year)
        except ValueError:
            return

        if year > max_year or year == max_year and order.index(season) >= order.index(max_season):
            max_year = year
            max_season = season

    return "{} {}".format(max_season, max_year)

class GhostWrapper():

    def __init__(self, fullpath, uploader):

        # set parameters as attributes #
        self.fullpath = fullpath
        self.uploader = uploader

        # sanity check filename #
        if not fullpath.lower().endswith(".gbx"):
            raise ValueError("Path must be a .gbx file")

        # parse with normal GBX-parser
        g = pygbx.Gbx(fullpath)
        ghost = g.get_class_by_id(pygbx.GbxType.CTN_GHOST)
        if not ghost:
            raise ValueError("No ghost found in GBX file")

        # compute mapname #
        if ghost.game_version.startswith("TmForever"):  
            mapname_from_filename = self._compute_map_from_filename()
        else:
            mapname_from_filename = None

        # compute filehash #
        f_hash = None
        content = None
        with open(fullpath, "rb") as f:

            # read file & compute #
            content = f.read()
            decoded_string = content.decode("ascii", errors="ignore")
            f_hash = hashlib.sha512(content).hexdigest()

        # general variables #
        self.filehash = f_hash
        self.ghost_id = ghost.id
        self.login = ghost.login
        self.race_time = ghost.race_time
        self.cp_times = ",".join(map(str, ghost.cp_times))
        self.upload_dt = datetime.datetime.now().isoformat()

        # game version #
        if ghost.game_version.startswith("TmForever"):  

            # set version and map #
            self.game = "tmnf"
            self.map_uid = mapname_from_filename
            self.login_uid_tm2020 = None

            # sanity check mapname for tmnf #
            if mapname_from_filename not in decoded_string:
                raise ValueError("Mapname indicated by filename does not match map in file")

        else:

            # set gameversion and compute from xml #
            self.game = "tm2020"
            self._set_from_2020()


    def _compute_map_from_filename(self):
        '''Compute the mapname from the filename if possible'''

        try:
            underscore_count = len(self.fullpath.split("_"))
            if underscore_count > 3 or underscore_count < 1:
                error_msg = "Filename unexpected number of '_' ({})".format(underscore_count)
                error_msg += ", does your (map-)name contain underscores? If yes remove them."
                raise ValueError(error_msg)
            mapname_from_filename = os.path.basename(self.fullpath).split("_")[1]
            if ".Replay" in mapname_from_filename:
                mapname_from_filename = mapname_from_filename.split(".Replay")[0]
        except IndexError:
            raise ValueError("Unexpected filename format. (IndexError)")
        return mapname_from_filename

    def _set_from_2020(self):
        '''Extract the XML-Header from TM2020-replays to set missing variables'''

        # Specify the pattern to match the XML-like string
        pattern = re.compile(rb'<header.*?</header>', re.DOTALL)
        
        # Extract XML-like strings from the binary file
        xml_strings = []
        with open(self.fullpath, 'rb') as binary_file:
            binary_data = binary_file.read()
            matches = re.findall(pattern, binary_data)
            xml_strings = [match.decode('utf-8') for match in matches]
        
        # set vars #
        xml_string = xml_strings[0]
        xml_dict = xmltodict.parse(xml_string)
        
        self.map_uid = xml_dict["header"]["map"]["@name"]
        print(self.map_uid)

        # load the name #
        with open(self.fullpath, "rb") as f:
            content = f.read()
            result = content.split(b"\0")[:100]

            # filter out empty bytes #
            result = list(filter(lambda x: x, result))

            # find the uid #
            uid_index = -1
            for i, el in enumerate(result):
                if self.login in el.decode("ascii", errors="ignore"):
                    uid_index = i
                    break

            if uid_index < 1:
                raise ValueError("Can't find user UID in replay file.")
            else:
                self.login_uid_tm2020 = self.login
                self.login = result[uid_index-1].strip(b"\x16").decode("utf-8")
