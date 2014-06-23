import json
import numpy
from heroes import HEROES

__author__ = 'yanbo'
import io
import os
from smoke.io.wrap import demo as io_wrap_demo
from smoke.replay import demo as replay_demo
from smoke.replay.const import Data
import pylab
import matplotlib
import matplotlib.image
import scipy.ndimage
import cPickle
from mapping import CoordinateMapper, HIRES_MAP_REF


MAX_COORD_INTEGER = 16384
here = os.path.dirname(os.path.abspath(__file__))
REPLAY_FOLDER = os.path.join(here, 'replay_files')

"""
entity     - something in-game that has networked information
DT         - a string that identifies the kind of entity at hand
cls        - an integer that identifies the kind of entity at hand
recv table - list of properties for entity of certain DT/cls; a template
"""


def get_hero_position(user_hero, position_x_index, position_y_index, position_vector_index, cell_width):

    cell_x = user_hero.get(position_x_index) * cell_width + user_hero.get(position_vector_index)[0]/128.
    cell_y = user_hero.get(position_y_index) * cell_width + user_hero.get(position_vector_index)[1]/128.

    return cell_x, cell_y


def get_current_replay():
    replay_list = []
    for replay_name in os.listdir(REPLAY_FOLDER):
        if replay_name.endswith(".dem"):
            replay_list.append(replay_name)

    print "Select replay which you wish to parse"

    for index, replay_name in enumerate(replay_list):
                print "{}) {}".format(index, replay_name)

    user_selection = None
    while True:
        user_input = raw_input('>')
        try:
            user_selection = int(user_input)
        except ValueError:
            print "Invalid input - Please enter a valid number 0-{}".format(len(replay_list))
        if user_selection is not None:
            if 0 <= user_selection < len(replay_list):
                break
            else:
                print "Invalid input - Please enter a valid number 0-{}".format(len(replay_list))
    return os.path.join(REPLAY_FOLDER, replay_list[user_selection])


def gather_data_for_heatmap():
    
    replay_path = get_current_replay()
    
    with io.open(replay_path, 'rb') as replay_file:
        demo_io = io_wrap_demo.Wrap(replay_file)
        demo_io.bootstrap()

        # we can seek on the raw underlying IO instead of parsing everything
        parse_mask = Data.All

        demo = replay_demo.Demo(demo_io, parse=parse_mask)

        # skipping to the start of the match
        demo.bootstrap()

        received_tables = demo.match.recv_tables
        class_info = demo.match.class_info

        game_meta_tables = received_tables.by_dt['DT_DOTAGamerulesProxy']
        game_status_index = game_meta_tables.by_name['dota_gamerules_data.m_nGameState']

        npc_info_table = received_tables.by_dt['DT_DOTA_BaseNPC']

        position_x_index = npc_info_table.by_name['m_cellX']
        position_y_index = npc_info_table.by_name['m_cellY']
        position_vector_index = npc_info_table.by_name['m_vecOrigin']

        # we need to calculate dimensions of the cell used on map, so we can determine coordinates
        base_entity_table = received_tables.by_dt['DT_BaseEntity']
        cell_info_index = base_entity_table.by_name['m_cellbits']

        user_hero_ehandle = None
        hero_positions = []

        cell_width = None
        mapper = None

        for match in demo.play():
            # first we need to wait for game to start
            game_meta = match.entities.by_cls[class_info['DT_DOTAGamerulesProxy']][0].state
            current_game_status = game_meta.get(game_status_index)

            if mapper is None:
                towers = match.entities.by_cls[class_info['DT_DOTA_BaseNPC_Tower']]
                mapper = CoordinateMapper(HIRES_MAP_REF, towers, received_tables)

            """
            m_nGameState

            1: Players loading in
            2: Pick/ban in CM (not sure about other modes)
            4: Pre-game (heroes selected but no creeps)
            5: Game clock hits 0:00 (creeps spawn)
            6: Game has ended (scoreboard)
            """
            if cell_width is None:
                base_game_info = match.entities.by_cls[class_info['DT_BaseEntity']][0].state
                cell_width = 1 << base_game_info.get(cell_info_index)

            if user_hero_ehandle is None and current_game_status == 5:
                match_heroes = get_heroes_names_and_ehandles(match.entities, class_info, received_tables)
                user_hero_ehandle = get_user_hero_ehandle(match_heroes)
            elif user_hero_ehandle is not None:
                user_hero_data = match.entities.by_ehandle[user_hero_ehandle].state
                hero_positions.append(get_hero_position(user_hero_data,
                                                        position_x_index,
                                                        position_y_index,
                                                        position_vector_index, cell_width))

        with open('data_position.pkl', 'wb') as output_file:
            cPickle.dump(hero_positions, output_file, protocol=-1)
        draw_heatmap(hero_positions, mapper)
        demo.finish()


def get_user_hero_ehandle(match_heroes):

    if len(match_heroes) != 10:
        return
    print "Select hero for which you wish to generate heatmap"
    for index, hero in enumerate(match_heroes):
        print "{}) {}".format(index, hero[0])
    user_selection = None
    while True:
        user_input = raw_input('>')
        try:
            user_selection = int(user_input)
        except ValueError:
            print "Invalid input - Enter a number from 0 to 9"
        if user_selection is not None and 0 <= user_selection <= 9:
            break
    print "Please wait while we generate heatmap"
    return match_heroes[user_selection][1]


def get_heroes_names_and_ehandles(entities, class_info, received_tables):
    world_data = entities.by_cls[class_info['DT_DOTA_PlayerResource']]
    rt = received_tables.by_dt['DT_DOTA_PlayerResource']
    current_data = world_data[0].state

    hero_data = []
    for i in range(10):
        hero_ehandle_index = rt.by_name['m_hSelectedHero.{:04d}'.format(i)]
        hero_id_index = rt.by_name['m_nSelectedHeroID.{:04d}'.format(i)]

        hero_id = current_data.get(hero_id_index)
        hero_ehandle = current_data.get(hero_ehandle_index)
        localized_hero_name = HEROES[hero_id - 2]['localized_name']

        hero_data.append((localized_hero_name, hero_ehandle))

    return hero_data


def get_overview_data(replay_path):
    with io.open(replay_path, 'rb') as replay_file:
        demo_io = io_wrap_demo.Wrap(replay_file)
        # returns offset to overview
        overview_offset = demo_io.bootstrap()

        # we can seek on the raw underlying IO instead of parsing everything
        replay_file.seek(overview_offset)

        demo = replay_demo.Demo(demo_io)
        demo.finish()

        return demo.match.overview


def rgb2gray(rgb):
    return numpy.dot(rgb[..., :3], (0.299, 0.587, 0.144))


def draw_heatmap(hero_positions=None, mapper=None):
    if hero_positions is None:
        with open('data_position.pkl', 'rb') as output_pickle:
            hero_positions = cPickle.load(output_pickle)

    background_map = matplotlib.image.imread('dota_map_high_res.jpg')

    # Grayscale the image so the contourf shows up more clearly
    background_map = rgb2gray(background_map)

    mapped_xs = []
    mapped_ys = []
    import matplotlib.pyplot as plt
    """"
    debug code start
    """
    raw_x = [x[0] for x in hero_positions]
    raw_y = [x[1] for x in hero_positions]

    plt.clf()
    plt.scatter(raw_x, raw_y)
    plt.show()
    """
    Debug code end
    """

    for x, y in hero_positions:
        mx, my = mapper.to_mapped(x, y)
        mapped_xs.append(mx)
        mapped_ys.append(my)

    plt.clf()
    plt.scatter(mapped_xs, mapped_ys)
    plt.show()
    plt.clf()
    pylab.imshow(background_map[::-1, :], origin='lower', cmap=pylab.cm.gray)
    #pylab.xlim(0, background_map.shape[1])
    #pylab.ylim(0, background_map.shape[0])
    pylab.scatter(mapped_xs, mapped_ys, color='blue')
    plt.show()
    return

    """
    End debug
    """

    blue_alpha = matplotlib.colors.LinearSegmentedColormap('BlueAlpha', {'red': ((0.0, 0.42, 0.42), (1.0, 0.03, 0.03)),
                                    'green': ((0.0, 0.68, 0.68), (1.0, 0.19, 0.19)),
                                    'blue': ((0.0, 0.84, 0.84), (1.0, 0.42, 0.42)),
                                    'alpha': ((0.0, 0.0, 0.0), (0.05, 0.0, 0.0), (0.10, 0.5, 0.5), (1.0, 1.0, 1.0))})

    orange_alpha = matplotlib.colors.LinearSegmentedColormap('OrangeAlpha', {'red': ((0.0, 1.0, 1.0), (1.0, 0.5, 0.5)),
                                    'green': ((0.0, 0.55, 0.55), (1.0, 0.15, 0.15)),
                                    'blue': ((0.0, 0.23, 0.23), (1.0, 0.0, 0.0)),
                                    'alpha': ((0.0, 0.0, 0.0), (0.05, 0.0, 0.0), (0.10, 0.5, 0.5), (1.0, 1.0, 1.0))})
    # Do a pixel-wide histogram followed by a strong Gaussian blur
    xedges = numpy.arange(0, background_map.shape[0], 1)
    yedges = numpy.arange(0, background_map.shape[1], 1)

    radiant_H, xedges, yedges = numpy.histogram2d(mapped_xs, mapped_ys, bins=(xedges, yedges))
    radiant_H = scipy.ndimage.gaussian_filter(radiant_H, sigma=50)
    X, Y = 0.5*(xedges[1:]+xedges[:-1]), 0.5*(yedges[1:]+yedges[:-1])
    # Re-orient so the (0,0) is in the radiant corner
    pylab.imshow(background_map[::-1, :], origin='lower', cmap=pylab.cm.gray)
    pylab.contourf(X, Y, numpy.log10(radiant_H.transpose()+1), 10, cmap=blue_alpha)
    pylab.contourf(X, Y, numpy.log10(dire_H.transpose()+1), 10, cmap=orange_alpha)
    pylab.xlim(0, background_map.shape[1])
    pylab.ylim(0, background_map.shape[0])
    pylab.gca().get_xaxis().set_visible(False)
    pylab.gca().get_yaxis().set_visible(False)
    pylab.tight_layout(0)
    pylab.savefig('radiant_dire_heatmap.png')
    pylab.close()


if __name__ == '__main__':
    # print json.dumps(get_overview_data(), indent=4)
    gather_data_for_heatmap()
    #draw_heatmap()