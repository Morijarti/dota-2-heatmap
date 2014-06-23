import copy
import numpy
import numpy.linalg

# Reference frame for in-game dota_camera_setpos (bottom-left corner)
DOTA_CAMERA_GETPOS_REF = {
    'dota_goodguys_tower1_top': {'x': -5461, 'y': 2010},
    'dota_goodguys_tower2_top': {'x': -5461, 'y': -683},
    'dota_goodguys_tower1_bot': {'x': 5600, 'y': -5927},
    'dota_goodguys_tower2_bot': {'x': 29, 'y': -5927},
    'dota_badguys_tower1_top': {'x': -4104, 'y': 6030},
    'dota_badguys_tower2_top': {'x': 588, 'y': 6030},
    'dota_badguys_tower1_bot': {'x': 6767, 'y': -1569},
    'dota_badguys_tower2_bot': {'x': 6767, 'y': 521},
}


# Reference frame for in-game vecOrigin (from starfox89)
INGAME_VECORIGIN_REF = {
    'dota_goodguys_tower1_top': {'x': -6096, 'y': 1840},
    'dota_goodguys_tower2_top': {'x': -6144, 'y': -832},
    'dota_goodguys_tower1_mid': {'x': -1504, 'y': -1376},
    'dota_goodguys_tower2_mid': {'x': -3512, 'y': -2776},
    'dota_goodguys_tower1_bot': {'x': 4928, 'y': -6080},
    'dota_goodguys_tower2_bot': {'x': -560, 'y': -6096},
    'ent_dota_fountain_good': {'x': -7456, 'y': -6960},
    'ent_dota_fountain_bad': {'x': 7472, 'y': 6912},
}


# Reference frame for 25-megapixel top-down PNG from
# http://www.reddit.com/r/DotA2/comments/1805d9/the_complete_dota2_map_25_megapixel_resolution/
# Remember to count the pixels from the bottom-left instead of the top-right corner (5087x4916)
HIRES_MAP_REF = {
    'dota_goodguys_tower1_top': {'x': 655, 'y': 4916 - 1967},
    'dota_goodguys_tower2_top': {'x': 638, 'y': 4916 - 2798},
    'dota_goodguys_tower3_top': {'x': 487, 'y': 4916 - 3576},
    'dota_goodguys_tower1_mid': {'x': 2082, 'y': 4916 - 2972},
    'dota_goodguys_tower2_mid': {'x': 1457, 'y': 4916 - 3407},
    'dota_goodguys_tower3_mid': {'x': 1113, 'y': 4916 - 3816},
    'dota_goodguys_tower1_bot': {'x': 4077, 'y': 4916 - 4442},
    'dota_goodguys_tower2_bot': {'x': 2369, 'y': 4916 - 4439},
    'dota_goodguys_tower3_bot': {'x': 1340, 'y': 4916 - 4444},
    'dota_badguys_tower1_top': {'x': 1081, 'y': 4916 - 670},
    'dota_badguys_tower2_top': {'x': 2558, 'y': 4916 - 671},
    'dota_badguys_tower3_top': {'x': 3650, 'y': 4916 - 747},
    'dota_badguys_tower1_mid': {'x': 2870, 'y': 4916 - 2441},
    'dota_badguys_tower2_mid': {'x': 3319, 'y': 4916 - 1885},
    'dota_badguys_tower3_mid': {'x': 3865, 'y': 4916 - 1383},
    'dota_badguys_tower1_bot': {'x': 4441, 'y': 4916 - 3071},
    'dota_badguys_tower2_bot': {'x': 4503, 'y': 4916 - 2465},
    'dota_badguys_tower3_bot': {'x': 4499, 'y': 4916 - 1613},
}


class CoordinateMapper(object):
    MAX_COORD_INTEGER = 16384

    def __init__(self, reference, towers, received_tables):
        '''Pass a reference dictionary of entity_name: {'x':x, 'y':y} coordinates.'''
        self._reference = copy.deepcopy(reference)
        # Add the cell coordinates into the reference
        remove = []

        tower_info_table = received_tables.by_dt['DT_DOTA_BaseNPC_Tower']
        position_x_index = tower_info_table.by_name['m_cellX']
        position_y_index = tower_info_table.by_name['m_cellY']
        position_vector_index = tower_info_table.by_name['m_vecOrigin']

        name_index = tower_info_table.by_name['m_iName']

        # we need to calculate dimensions of the cell used on map, so we can determine coordinates
        cell_info_index = tower_info_table.by_name['m_cellbits']

        for name, val in self._reference.iteritems():
            for base_entity in towers:
                state = base_entity.state
                state_name = state.get(name_index)
                if state_name == name:
                    cellwidth = 1 << state.get(cell_info_index)
                    val['worldX'] = state.get(position_x_index) + state.get(position_vector_index)[0] / 128.

                    val['worldY'] = state.get(position_y_index) + state.get(position_vector_index)[1] / 128.
                    break
            else:
                remove.append(name)
        for name in remove:
            del self._reference[name]

        """ DEBUG CODE """
        # some code to visualise map position in order to see if we got them right
        import matplotlib.pyplot as plt

        raw_x = [v['worldX'] for v in self._reference.itervalues()]
        raw_y = [v['worldY'] for v in self._reference.itervalues()]

        plt.clf()
        plt.title("Tower position")
        plt.scatter(raw_x, raw_y)
        plt.show()
        """
        END DEBUG CODE
        """

        self._generate_mapping()

    def _generate_mapping(self):
        Ax = numpy.vstack([[v['worldX'] for v in self._reference.itervalues()], numpy.ones(len(self._reference))]).T
        self._scale_x, self._offset_x = numpy.linalg.lstsq(Ax, [v['x'] for v in self._reference.itervalues()])[0]
        Ay = numpy.vstack([[v['worldY'] for v in self._reference.itervalues()], numpy.ones(len(self._reference))]).T
        self._scale_y, self._offset_y = numpy.linalg.lstsq(Ay, [v['y'] for v in self._reference.itervalues()])[0]

    def to_cell(self, mapped_x, mapped_y):
        return (mapped_x - self._offset_x) / self._scale_x, (mapped_y - self._offset_y) / self._scale_y

    def to_mapped(self, cell_x, cell_y):
        return self._scale_x * cell_x + self._offset_x, self._scale_y * cell_y + self._offset_y


if __name__ == "__main__":
    """
    mapper = CoordinateMapper(HIRES_MAP_REF, earlytick)

    # Load the background map
    import matplotlib.image

    background_map = matplotlib.image.imread('../dota_map.png')

    # Plot the least-squares fitting for the mapping
    import pylab

    pylab.plot([v['worldX'] for v in mapper._reference.values()], [v['x'] for v in mapper._reference.values()], 'bo',
               label='X')
    line_xs = numpy.arange(min([v['worldX'] for v in mapper._reference.values()]),
                           max([v['worldX'] for v in mapper._reference.values()]))
    pylab.plot(line_xs, line_xs * mapper._scale_x + mapper._offset_x, 'b-', label='LSQ-X')
    pylab.plot([v['worldY'] for v in mapper._reference.values()], [v['y'] for v in mapper._reference.values()], 'ko',
               label='Y')
    line_ys = numpy.arange(min([v['worldY'] for v in mapper._reference.values()]),
                           max([v['worldY'] for v in mapper._reference.values()]))
    pylab.plot(line_ys, line_ys * mapper._scale_y + mapper._offset_y, 'k-', label='LSQ-Y')
    pylab.xlabel('World Coordinate')
    pylab.ylabel('Pixel')
    pylab.legend(loc='upper left')
    pylab.savefig('lsq.png')
    pylab.close()
    """
    pass
