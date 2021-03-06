"""
This python file deals with all Othello game logic. This includes saving and loading
games as well as interfacing with the GUI.
"""

from copy import deepcopy
from os import path, remove, listdir, mkdir
from tempfile import NamedTemporaryFile
from random import getrandbits
from time import time, sleep

from Constants import *


class BoardError(Exception):
    """A custom exception used to catch board errors."""

    pass


class HashedBoard:
    """A special board that can be stored in a dictionary to save pre-calculated AI moves."""

    def __init__(self, board, hash_num):
        self.board = board
        self.hash_num = hash_num
        self.depth = None
        self.value = None
        self.type_of_info = None

    def __hash__(self):
        """
        The hash function is used in a python dictionary (hash table),
        this function ensures a zobrist hash of the board is returned.
        """

        return self.hash_num

    def __eq__(self, other):
        """
        Used for the python dictionary to ensure two boards in the same position
        are the same board and not a collision.
        """

        return self.board == other.board

    def __deepcopy__(self, memo=None):
        """Used to copy the board correctly."""

        return HashedBoard(deepcopy(self.board), self.hash_num)


class Othello:
    """An abstract class that deals with all Othello logic"""

    def __init__(self, board=None):
        if board is not None:
            self.board = board
        else:
            self.board = LAST_BOARD
            board = [[START_POS.get((x, y), "E") for x in range(BOARD_SIZE)] for y in range(BOARD_SIZE)]
            # Not directly assigning so I can keep same reference for other files to use the last board
            for y in range(BOARD_SIZE):
                for x in range(BOARD_SIZE):
                    self.board[y][x] = board[y][x]

        self.possible_moves = {"W": {}, "B": {}}
        self.board_change()

    def flip(self, pos):
        """Flips a piece at a certain position"""

        self.board[pos[1]][pos[0]] = FLIP_RULE[self.board[pos[1]][pos[0]]]

    def line_iterator(self, pos, current_colour, check_lines):
        """A custom line iterator that checks whether a certain piece being placed needs to flip other pieces. """

        for (step_x, step_y) in check_lines:
            done_first_iter, flip_line_holds, i = False, False, 0

            for i in range(1, BOARD_SIZE):  # Check if flip can be made
                x, y = step_x * i + pos[0], step_y * i + pos[1]
                if not (0 <= x < 8 and 0 <= y < 8):
                    break
                if not done_first_iter:
                    done_first_iter = True
                    if self.board[y][x] != FLIP_RULE[current_colour]:
                        break
                elif self.board[y][x] == current_colour:  # Check line end for empty
                    flip_line_holds = True
                    break
                elif self.board[y][x] == "E":
                    break

            if flip_line_holds:  # Once we know the line holds iterate through again to get x and y pos
                for z in range(1, i):  # Flip
                    x, y = step_x * z + pos[0], step_y * z + pos[1]
                    yield x, y, (step_x, step_y)

    def check_flip_line(self, pos, current_colour, check_line):
        """This checks if a certain possible flip leads to a valid result"""

        try:
            return next(self.line_iterator(pos, current_colour, [check_line]))[2]
        except StopIteration:
            return None

    def flip_line(self, pos, current_colour):
        """This uses the pre calculated values to flip pieces."""

        for (x, y, step_tup) in self.line_iterator(pos, current_colour, self.possible_moves[current_colour][pos]):
            self.flip((x, y))

    def place(self, pos, current_colour):
        """Place the piece, flips the correct pieces and then signals a board change."""

        self.board[pos[1]][pos[0]] = current_colour
        self.flip_line(pos, current_colour)
        self.board_change()
        return pos

    def board_change(self):
        """
        Prepares for pre-calculation of values by removing positions that are not placeable,
        such as places with pieces or empty positions surrounded by other empty positions
        """

        self.possible_moves = {"W": {}, "B": {}}
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                if self.board[y][x] == "E":
                    for adjacency in self.adjacent((x, y)):
                        if adjacency[0] == "W":
                            check_flip_line = self.check_flip_line((x, y), "B", adjacency[1])
                            if check_flip_line:
                                if (old := self.possible_moves["B"].get((x, y))) is not None:  # Checked with timeit
                                    self.possible_moves["B"][(x, y)] = old + [check_flip_line]
                                else:
                                    self.possible_moves["B"][(x, y)] = [check_flip_line]
                        elif adjacency[0] == "B":
                            check_flip_line = self.check_flip_line((x, y), "W", adjacency[1])
                            if check_flip_line:
                                if (old := self.possible_moves["W"].get((x, y))) is not None:
                                    self.possible_moves["W"][(x, y)] = old + [check_flip_line]
                                else:
                                    self.possible_moves["W"][(x, y)] = [check_flip_line]

    def adjacent(self, pos):
        """
        Returns all pieces around a certain position whilst ensuring they are valid.
        By using an iterator instead of returning all positions, we can run
        the algorithm much faster as in most cases not every position will
        need to be checked.
        """

        for (step_x, step_y) in FLIP_LINES:
            x, y = pos[0] + step_x, pos[1] + step_y
            if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE and self.board[y][x] != "E":
                yield self.board[y][x], (step_x, step_y)

    def can_be_placed(self, pos, current_colour):
        """
        This ensures that all positions given will be correct possible positions.
        Returns the formatted position as well as whether it is possible.
        """

        try:
            pos = int(pos[0]), int(pos[1])
        except ValueError:
            return pos, False

        if 0 <= pos[0] < BOARD_SIZE and 0 <= pos[1] < BOARD_SIZE:
            if pos in self.possible_moves[current_colour].keys():
                return pos, True
        return pos, False

    def end_game_iterator(self, colour="B"):
        """
        Another custom iterator that returns the next colour that plays,
        the default argument is the starting colour.
        """

        while True:
            if len(self.possible_moves[colour]):  # Check if a move can be played
                yield colour
                colour = FLIP_RULE[colour]
            elif len(self.possible_moves[FLIP_RULE[colour]]):  # Preemptive turn change
                colour = FLIP_RULE[colour]
                yield colour
            else:
                break

    def count_pieces(self):
        """Counts all the pieces on a board and returns that count."""

        count = {"W": 0, "B": 0, "E": 0}
        for x in range(BOARD_SIZE):
            for y in range(BOARD_SIZE):
                count[self.board[x][y]] += 1
        return count

    def print_board(self):
        """A function used to print the board, it must be implemented in this classes' children."""

        raise BoardError("Must be implemented.")

    def evaluate_winner(self):
        """A function used to evaluate the board, it should be implemented in this classes' children."""

        quit()


class HashedLocalVersus(Othello):
    """
    Class used to update the zobrist hash for the AI.
    The zobrist hash is a special hash used for games,
    the hash XORs a random number depending on the piece and location of it everytime a piece moves.
    This allows hashes to be produced very quickly as they do not need to be recomputed for each move.
    """

    def __init__(self, board_state: HashedBoard, possible_moves, table):
        self.board_state = board_state
        self.board = self.board_state.board
        self.possible_moves = possible_moves
        self.table = table

    def __deepcopy__(self, memo=None):
        """Allows for efficient copying of the game state."""

        return HashedLocalVersus(deepcopy(self.board_state), self.possible_moves,
                                 self.table)  # self.possible_moves and self.table are never changed during runtime

    def place(self, pos, current_colour):
        """
        Place the piece, flips the correct pieces and then signals a board change.
        When placing a piece it will XOR the correct numbers to create the correct hash.
        """

        self.board[pos[1]][pos[0]] = current_colour
        self.board_state.hash_num = self.board_state.hash_num ^ self.table[pos[1] * BOARD_SIZE + pos[0]][
            XOR_INDICES["E"]]
        self.board_state.hash_num = self.board_state.hash_num ^ self.table[pos[1] * BOARD_SIZE + pos[0]][
            XOR_INDICES[current_colour]]
        self.flip_line(pos, current_colour)
        self.board_change()
        return pos

    def flip(self, pos):
        """
        Flips a piece at a certain position.
        When flipping a piece it will XOR the correct numbers to create the correct hash.
        """

        current_colour = self.board[pos[1]][pos[0]]
        self.board[pos[1]][pos[0]] = FLIP_RULE[current_colour]
        self.board_state.hash_num = self.board_state.hash_num ^ self.table[pos[1] * BOARD_SIZE + pos[0]][
            XOR_INDICES[current_colour]]
        self.board_state.hash_num = self.board_state.hash_num ^ self.table[pos[1] * BOARD_SIZE + pos[0]][
            XOR_INDICES[FLIP_RULE[current_colour]]]


class SaveGame(Othello):
    """A class to save games."""

    def __init__(self):
        self.init = True  # Used to check if save is ran for the first time.
        self.saving_name = None
        super().__init__()

    def save(self, instruction):
        """
        Creates a file that has an unused name and then saves to that file every time a new piece is placed.
        The saved file contains all instructions to get to the current board state, assuming same starting piece.
        """

        if self.init:
            try:
                save_file = NamedTemporaryFile(mode="a", delete=False, dir=SAVE_DIR, suffix=SAVE_SUFFIX)
            except FileNotFoundError:
                mkdir(SAVE_DIR)
                save_file = NamedTemporaryFile(mode="a", delete=False, dir=SAVE_DIR, suffix=SAVE_SUFFIX)
            self.saving_name = save_file.name
            save_file.close()

            try:
                # Check if more than 15 saved games are stored
                files = listdir(SAVE_DIR)
                if len(files) > 14:
                    files = sorted(listdir(SAVE_DIR), reverse=True, key=lambda x: path.getmtime(path.join(SAVE_DIR, x)))[14:]
                    for file in files:
                        remove(path.join(SAVE_DIR, file))
            except FileNotFoundError:
                print("Error encountered... Are you running the same Othello process twice?")

            self.init = False
        instruction = str(instruction[0]) + "," + str(instruction[1]) + "\n"
        with open(path.join(SAVE_DIR, self.saving_name), 'a') as file:
            file.write(instruction)


class LocalVersus(SaveGame):
    """A class used to interface with the GUI. Used in local games."""

    def __init__(self, gui_to_oth, oth_to_gui):
        self.gui_to_oth = gui_to_oth
        self.oth_to_gui = oth_to_gui
        self.playing_colour = "B"
        super().__init__()
        self.play()

    def get_pos(self):
        """Gets the position from the GUI."""

        while True:
            answer = self.gui_to_oth.get(True)
            if answer[0] == LOCAL_IO["Click"]:
                return answer[1]
            elif answer[0] == LOCAL_IO["End"]:
                quit()
            else:
                self.gui_to_oth.put(answer)

    def play(self):
        """Used to play game, changes colour, places pieces from GUI, and saves plays."""

        for self.playing_colour in self.end_game_iterator(self.playing_colour):
            self.print_board()
            while not (tup := self.can_be_placed(self.get_pos(), self.playing_colour))[1]:  # Walrus op for the win
                pass
            self.save(tup[0])
            self.place(tup[0], self.playing_colour)
        self.print_board()
        self.evaluate_winner()

    def print_board(self):
        """Prints the board by sending it to the GUI."""

        self.oth_to_gui.put((LOCAL_IO["Print"], self.board))
        self.oth_to_gui.put((LOCAL_IO["Colour"], self.playing_colour))
        self.oth_to_gui.put((LOCAL_IO["Possible"], self.possible_moves[self.playing_colour]))
        count = self.count_pieces()
        del count["E"]
        self.oth_to_gui.put((LOCAL_IO["Count"], count))

    def evaluate_winner(self):
        """Evaluates the winner for the GUI to congratulate winner."""

        count = self.count_pieces()
        del count["E"]
        self.oth_to_gui.put((LOCAL_IO["Winner"], count))
        quit()


class NetworkVersus(LocalVersus):
    """Interfaces with the GUI, used for LAN games."""

    def __init__(self, gui_and_network_to_oth, oth_to_gui, oth_to_network, save_name):
        self.colour = self.get_colour(gui_and_network_to_oth)
        self.oth_to_network = oth_to_network
        self.save_name = save_name
        super(NetworkVersus, self).__init__(gui_and_network_to_oth, oth_to_gui)

    def get_pos(self):
        """Gets the position from the GUI or Network."""

        while True:
            answer = self.gui_to_oth.get(True)
            if answer[0] == LOCAL_IO["Click"]:
                if self.playing_colour == self.colour:
                    self.oth_to_network.put((LOCAL_IO["Net_Send"], answer[1]))
                    return answer[1]
            elif answer[0] == LOCAL_IO["End"]:
                quit()
            elif answer[0] == LOCAL_IO["Net_Click"]:
                if self.playing_colour != self.colour:
                    return answer[1]
            elif answer[0] == LOCAL_IO["Net_Load"]:
                self.load(answer[1])
            else:
                self.gui_to_oth.put(answer)

    @staticmethod
    def get_colour(gui_to_oth):
        """Gets the correct colour from the Network thread."""

        while True:
            answer = gui_to_oth.get(True)
            if answer[0] == LOCAL_IO["Net_Colour"]:
                return answer[1]
            elif answer[0] == LOCAL_IO["End"]:
                exit()
            else:
                gui_to_oth.put(answer)

    def print_board(self):
        """Prints the board to the GUI. Removes the moves when you are not playing."""

        self.oth_to_gui.put((LOCAL_IO["Print"], self.board))
        self.oth_to_gui.put((LOCAL_IO["Colour"], self.playing_colour))
        if self.playing_colour != self.colour:
            self.oth_to_gui.put((LOCAL_IO["Possible"], {}))
        else:
            self.oth_to_gui.put((LOCAL_IO["Possible"], self.possible_moves[self.playing_colour]))
        count = self.count_pieces()
        del count["E"]
        self.oth_to_gui.put((LOCAL_IO["Count"], count))

    @staticmethod
    def get_pos_from_file(line):
        """Gets the instruction back from the file."""

        line = line.split(",")
        return int(line[0]), int(line[1])

    def load(self, commands):
        """Loads the save file."""

        for line, self.playing_colour in zip(commands.splitlines(), self.end_game_iterator(self.playing_colour)):
            if not (tup := self.can_be_placed(self.get_pos_from_file(line), self.playing_colour))[1]:  # Walrus op
                raise BoardError("Incorrect Board")
            self.save(tup[0])
            self.place(tup[0], self.playing_colour)
        self.playing_colour = FLIP_RULE[self.playing_colour]
        self.print_board()

    def play(self):
        """Starts playing."""
        if self.save_name is not None:
            self.load(self.save_name)
        super(NetworkVersus, self).play()


class AI(LocalVersus):
    """A class used for the AI of the game."""

    def __init__(self, gui_to_oth, oth_to_gui, difficulty):
        self.table = [[getrandbits(64) for _ in range(3)] for _ in range(BOARD_SIZE * BOARD_SIZE)]
        # Creates the zobrist hash table that allows zobrist hashes to be created.

        self.ai_colour = "W"
        self.search_dict = {}
        self.difficulty, self.search_time = DIFFICULTY_TO_AI_CONFIG[difficulty]
        super(AI, self).__init__(gui_to_oth, oth_to_gui)

    def play(self):
        """Used to play game, changes colour, places pieces from GUI, and saves plays."""

        for self.playing_colour in self.end_game_iterator(self.playing_colour):
            self.print_board()
            if self.playing_colour != self.ai_colour:
                while not (tup := self.can_be_placed(self.get_pos(), self.playing_colour))[1]:  # Walrus op for the win
                    pass
            else:
                tup = (self.ai_play(), True)
            self.save(tup[0])
            self.place(tup[0], self.playing_colour)
        self.print_board()
        self.evaluate_winner()

    def print_board(self):
        """Prints the board by sending it to the GUI."""

        self.oth_to_gui.put((LOCAL_IO["Print"], self.board))
        self.oth_to_gui.put((LOCAL_IO["Colour"], self.playing_colour))
        if self.playing_colour == self.ai_colour:
            self.oth_to_gui.put((LOCAL_IO["Possible"], {}))
        else:
            self.oth_to_gui.put((LOCAL_IO["Possible"], self.possible_moves[self.playing_colour]))
        count = self.count_pieces()
        del count["E"]
        self.oth_to_gui.put((LOCAL_IO["Count"], count))

    def ai_play(self):
        """Run when the AI should play."""

        if self.difficulty is None:
            score, best_move = AI.minimax(self.get_hash_version(), float('-inf'), float('+inf'), True, True, 1, {})
            sleep(1)
        else:
            score, best_move = AI.iterative_deepening(self.get_hash_version(), self.difficulty, self.search_time,
                                                      self.search_dict)

            self.search_dict = {k: (v[0], v[1], (v[2] - 2), v[3]) for (k, v) in self.search_dict.items() if v[2] >= 3}
        return best_move

    def get_hash_version(self):
        """Creates a zobrist hash board of the current board."""

        zobrist_hash = 0
        for y in range(BOARD_SIZE):
            for x in range(BOARD_SIZE):
                zobrist_hash ^= self.table[y * BOARD_SIZE + x][XOR_INDICES[self.board[y][x]]]   # XOR

        return HashedLocalVersus(HashedBoard(deepcopy(self.board), zobrist_hash), self.possible_moves, self.table)

    @staticmethod
    def mtdf(board: HashedLocalVersus, first_guess, lookahead, search_dict):
        """
        This is a modified minimax algorithm called Memory-enhanced Test Driver.
        It works by continually testing certain minimax values to try "zoom" into the correct minimax value.
        Since it runs the minimax algorithm several times it must ensure that the minimax algorithm uses memory
        to save previously calculated values.
        """

        guess = first_guess
        upper_bound = float('+inf')
        lower_bound = float('-inf')
        while lower_bound < upper_bound:
            if guess == lower_bound:
                beta = guess + 1
            else:
                beta = guess
            guess, move = AI.minimax(board, beta - 1, beta, True, True, lookahead, search_dict)
            if guess < beta:
                upper_bound = guess
            else:
                lower_bound = guess
        return guess, move

    @staticmethod
    def iterative_deepening(board: HashedLocalVersus, difficulty, search_time, search_dict):
        """
        Iterative deepening will bit by bit increase the depth of the search
        this ensures that the algorithm can be stopped if it takes too long.
        """

        first_guess, even_guess, odd_guess = 0, 0, 0
        start_time = time()
        for depth in range(1, difficulty):
            if depth % 2 == 0:
                first_guess, move = AI.mtdf(board, even_guess, depth, search_dict)
                even_guess = first_guess
            else:
                first_guess, move = AI.mtdf(board, odd_guess, depth, search_dict)
                odd_guess = first_guess
            if start_time + search_time <= time():
                break
            if start_time + 1 > time():
                sleep(1.5)
        return first_guess, move

    @staticmethod
    def check_if_terminal(board: HashedLocalVersus):
        """Will check if the board is in an end state."""

        if board.possible_moves["B"] == board.possible_moves["W"] == {}:
            return True
        elif board.possible_moves["B"] == {} or board.possible_moves["W"] == {}:
            count = list(
                (v, k) for (k, v) in sorted(board.count_pieces().items(), key=lambda item: item[1], reverse=True) if
                k != "E")  # Sort list of piece count in descending order
            if count[1][0] == 0:
                return True
            else:
                return False
        else:
            return False

    @staticmethod
    def terminal_utility(othello: HashedLocalVersus):
        """Counts the score of a board if an end state."""

        count = list(
            (v, k) for (k, v) in sorted(othello.count_pieces().items(), key=lambda item: item[1], reverse=True) if
            k != "E")  # Sort list of piece count in descending order
        if count[0][0] == count[1][0]:  # Try
            return 0
        elif count[0][1] == "W":  # 85 used as max from heuristic is 85
            return 85 + count[0][0] - count[1][0]
        else:
            return -85 - count[0][0] + count[1][0]

    @staticmethod
    def heuristic_utility(othello: HashedLocalVersus):
        """
        Calculates the heuristic utility of a board. The board values are based off this paper:
        https://courses.cs.washington.edu/courses/cse573/04au/Project/mini1/RUSSIA/Final_Paper.pdf
        """

        count = othello.count_pieces()
        heuristic_piece_count = (count["W"] - count["B"]) / (count["W"] + count["B"])

        white_move_count = len(othello.possible_moves["W"])
        black_move_count = len(othello.possible_moves["B"])

        heuristic_mobility = (white_move_count - black_move_count) / (white_move_count + black_move_count)

        piece_to_heuristic = {"W": 1, "B": -1, "E": 0}
        total_corners_captured = (abs(piece_to_heuristic[othello.board[0][0]]) +
                                  abs(piece_to_heuristic[othello.board[BOARD_SIZE - 1][0]]) +
                                  abs(piece_to_heuristic[othello.board[0][BOARD_SIZE - 1]]) +
                                  abs(piece_to_heuristic[othello.board[BOARD_SIZE - 1][BOARD_SIZE - 1]]))
        if total_corners_captured != 0:  # Division by zero error
            heuristic_corner_capture = (
                                               piece_to_heuristic[othello.board[0][0]] +
                                               piece_to_heuristic[othello.board[BOARD_SIZE - 1][0]] +
                                               piece_to_heuristic[othello.board[0][BOARD_SIZE - 1]] +
                                               piece_to_heuristic[othello.board[BOARD_SIZE - 1][
                                                   BOARD_SIZE - 1]]) / total_corners_captured
        else:
            heuristic_corner_capture = 0

        # Check for stability (Using an estimation as computationally expensive to correctly calculate
        if othello.board[0][0] != 'E' or othello.board[0][BOARD_SIZE - 1] != 'E' or othello.board[BOARD_SIZE - 1][0] != 'E' or \
                othello.board[BOARD_SIZE - 1][BOARD_SIZE - 1] != 'E':
            tracked_black = set((y, x) for x in range(BOARD_SIZE) for y in range(BOARD_SIZE) if othello.board[y][x] == 'B')
            tracked_white = set((y, x) for x in range(BOARD_SIZE) for y in range(BOARD_SIZE) if othello.board[y][x] == 'W')
            for y, x, position in AI.stability_iterator():
                if position == 1:
                    last_black_opposing = 'N'  # N for None
                    last_white_opposing = 'N'
                elif position == 2:
                    last_black_opposing = 'N'
                    last_white_opposing = 'N'
                    if len(tracked_black) == 0 and len(tracked_white) == 0:
                        break
                if last_black_opposing != 'N':
                    if othello.board[y][x] == 'E':
                        if len(last_black_empty) > 0:
                            tracked_black -= last_black_empty
                            last_black_empty = set()
                        last_black_opposing = 'E'

                    elif othello.board[y][x] == 'W':
                        if len(last_black_empty) > 0:
                            if last_black_opposing == 'E':
                                tracked_black -= last_black_empty
                                last_black_empty = set()
                        else:
                            last_black_opposing = 'W'
                    else:
                        last_black_empty.add((y, x))
                elif othello.board[y][x] == 'E' or othello.board[y][x] == 'W':
                    last_black_opposing = othello.board[y][x]
                    last_black_empty = set()

                if last_white_opposing != 'N':
                    if othello.board[y][x] == 'E':
                        if len(last_white_empty) > 0:
                            tracked_white -= last_white_empty
                            last_white_empty = set()
                        last_white_opposing = 'E'

                    elif othello.board[y][x] == 'B':
                        if len(last_white_empty) > 0:
                            if last_white_opposing == 'E':
                                tracked_white -= last_white_empty
                                last_white_empty = set()
                        else:
                            last_white_opposing = 'B'
                    else:
                        last_white_empty.add((y, x))
                elif othello.board[y][x] == 'E' or othello.board[y][x] == 'B':
                    last_white_opposing = othello.board[y][x]
                    last_white_empty = set()
        else:
            tracked_black = []
            tracked_white = []

        black_stability = len(tracked_black)
        white_stability = len(tracked_white)

        if white_stability + black_stability != 0:  # Division by zero error
            heuristic_stability = (white_stability - black_stability) / (white_stability + black_stability)
        else:
            heuristic_stability = 0

        return 30 * heuristic_corner_capture + heuristic_mobility * 5 + heuristic_stability * 25 + heuristic_piece_count * 25

    @staticmethod
    def stability_iterator():
        """
        Will iterate through every move line to remove unstable pieces from stability list.
        The position indicates extra code that should be run at certain points in time.
        0 means do nothing, 1 reset last_known, 2 do things in 1 and check if there are still stable pieces.
        """
        position = 0
        for y in range(BOARD_SIZE):
            if position == 0:
                position = 1
            for x in range(BOARD_SIZE):
                yield y, x, position
                position = 0

        position = 2
        for x in range(BOARD_SIZE):
            if position == 0:
                position = 1
            for y in range(BOARD_SIZE):
                yield y, x, position
                position = 0

        position = 2
        for y, x in LEFT_RIGHT_DIAGONALS:
            if position == 0:
                position = 1
            while y < BOARD_SIZE and x < BOARD_SIZE:
                yield y, x, position
                position = 0
                y += 1
                x += 1

        position = 2
        for y, x in RIGHT_LEFT_DIAGONALS:
            if position == 0:
                position = 1
            while y < BOARD_SIZE and x >= 0:
                yield y, x, position
                position = 0
                y += 1
                x += -1

    @staticmethod
    def dumb_line_iterator(y, x, line_diff):  # working in (y,x)
        """Will iterate through a line without caring about the pieces it iterates through."""

        while 0 >= x > BOARD_SIZE and 0 >= y > BOARD_SIZE:
            yield y, x
            y += line_diff[0]
            x += line_diff[1]

    @staticmethod
    def minimax(board: HashedLocalVersus, alpha, beta, maximising_player, initial, lookahead, searched_moves):
        """
        The minimax algorithm with memory to ensure that values are not computed several times.
        This version uses alpha beta to cut values that would not affect the final value.
        Some of the code is based off this thread:
        https://www.gamedev.net/forums/topic.asp?topic_id=503234
        """

        if (search := searched_moves.get(board.board_state)) is not None and search[2] >= lookahead:

            value, type_of_info, depth, move = search
            if type_of_info == 1:
                if initial:
                    return value, move
                return value
            elif type_of_info == 0:  # Lower bound
                alpha = max(alpha, value)
            elif type_of_info == 2:  # Upper bound
                beta = min(beta, value)
            if alpha >= beta:
                if initial:
                    return value, move
                return value
            check_move_first = move
        else:
            check_move_first = None

        if AI.check_if_terminal(board):
            return AI.terminal_utility(board)
        elif lookahead <= 0:
            return AI.heuristic_utility(board)

        if maximising_player:
            score = float('-inf')
            sorted_actions = AI.sort_actions(board.possible_moves["W"].keys(), board, check_move_first, 1, "W")
            a = alpha
            for new_board, possible_action in sorted_actions:
                # Ensures the move check_move_first is checked first
                evaluation = AI.minimax(new_board, a, beta, len(new_board.possible_moves["B"]) == 0, False,
                                        lookahead - 1, searched_moves)
                if score < evaluation:
                    action = possible_action
                score = max(score, evaluation)
                a = max(a, score)
                if a >= beta:
                    break

        else:
            score = float('inf')
            sorted_actions = AI.sort_actions(board.possible_moves["B"].keys(), board, check_move_first, -1, "B")
            b = beta
            for new_board, possible_action in sorted_actions:
                evaluation = AI.minimax(new_board, alpha, b, len(new_board.possible_moves["W"]) != 0, False,
                                        lookahead - 1, searched_moves)
                if score > evaluation:
                    action = possible_action
                score = min(score, evaluation)
                b = min(b, score)
                if b <= alpha:
                    break

        if score <= alpha:
            searched_moves[board.board_state] = (score, 2, lookahead, action)
        if alpha < score < beta:
            searched_moves[board.board_state] = (score, 1, lookahead, action)
        if score >= beta:
            searched_moves[board.board_state] = (score, 0, lookahead, action)

        if initial:
            return score, action
        else:
            return score

    @staticmethod
    def sort_actions(actions, board, check_move_first, factor, player):
        """
        Sorts the actions that can be done on an initial board in a manner so that
        the first one is most likely to be the board layout with the highest score.
        """

        boards = []
        for action in actions:
            new_board = deepcopy(board)
            new_board.place(action, player)
            boards.append((new_board, action))
        return sorted(boards, reverse=True, key=lambda x: (x[1] == check_move_first)*50000 + AI.utility(x[0],x[1], factor))

    @staticmethod
    def utility(board, move, factor):
        """Will quickly return an estimation of a board's more computationally expensive estimation of utility."""

        if AI.check_if_terminal(board):
            return AI.terminal_utility(board) * 10 * factor
        else:
            return BOARD_WEIGHT[move[0]][move[1]]


class LoadLocalVersus(LocalVersus):
    """
    A class used to load boards from the save files and then
    just play as if it were a normal GUI class.
    """

    def __init__(self, gui_to_oth, oth_to_gui, save_name, line_count):
        self.save_name = save_name
        self.line_count = line_count
        super(LoadLocalVersus, self).__init__(gui_to_oth, oth_to_gui)

    @staticmethod
    def get_pos_from_file(line):
        """Gets the instruction back from the file."""

        line = line.split(",")
        return int(line[0]), int(line[1])

    def load(self):
        """Loads the save file."""

        with open(path.join(SAVE_DIR, self.save_name), 'r') as file:
            commands = file.readlines()
        line_count = 0
        for line, self.playing_colour in zip(commands, self.end_game_iterator(self.playing_colour)):
            if line_count == self.line_count:
                break
            line_count += 1
            if not (tup := self.can_be_placed(self.get_pos_from_file(line), self.playing_colour))[1]:  # Walrus op
                raise BoardError("Incorrect Board")
            self.save(tup[0])
            self.place(tup[0], self.playing_colour)
        self.playing_colour = FLIP_RULE[self.playing_colour]

    def play(self):
        """Start function so that it can play normally. (By loading the file first)"""

        self.load()
        super(LoadLocalVersus, self).play()


class LoadAI(AI):
    """
    A class used to load boards from the save files and then
    just play as if it were a normal GUI class.
    """

    def __init__(self, gui_to_oth, oth_to_gui, save_name, line_count, difficulty):
        self.save_name = save_name
        self.line_count = line_count
        super(LoadAI, self).__init__(gui_to_oth, oth_to_gui, difficulty)

    @staticmethod
    def get_pos_from_file(line):
        """Gets the instruction back from the file."""

        line = line.split(",")
        return int(line[0]), int(line[1])

    def load(self):
        """Loads the save file."""

        with open(path.join(SAVE_DIR, self.save_name), 'r') as file:
            commands = file.readlines()
        line_count = 0
        for line, self.playing_colour in zip(commands, self.end_game_iterator(self.playing_colour)):
            if line_count == self.line_count:
                break
            line_count += 1
            if not (tup := self.can_be_placed(self.get_pos_from_file(line), self.playing_colour))[1]:  # Walrus op
                raise BoardError("Incorrect Board")
            self.save(tup[0])
            self.place(tup[0], self.playing_colour)
        self.playing_colour = FLIP_RULE[self.playing_colour]

    def play(self):
        """Start function so that it can play normally. (By loading the file first)"""

        self.load()
        super(LoadAI, self).play()


class Text(Othello):
    """Currently unused class, that was used to quickly test and prototype logic."""

    def __init__(self):
        super(Text, self).__init__()

    def print_board(self):
        """Prints the board in text form."""

        board_copy = [[x.replace("E", " ") for x in self.board[y]] for y in range(BOARD_SIZE)]
        print(*(list(" ") + list(range(BOARD_SIZE))), sep=" | ", end=" |\n")
        for x in range(BOARD_SIZE):
            print(*(list(str(x)) + board_copy[x]), sep=" | ", end=" |\n")

    def evaluate_winner(self):
        """Evaluate winner in text."""

        try:
            next(self.end_game_iterator())  # Check if game has ended
        except StopIteration:
            pass
        else:
            raise BoardError("Game has not ended.")

        count = list((v, k) for (k, v) in sorted(self.count_pieces().items(), key=lambda item: item[1], reverse=True) if
                     k != "E")  # Sort list in descending order
        if count[0][0] == count[1][0]:
            print("The game ended in a try." + " You both had: " + str(count[0][0]) + " pieces.")
        else:
            print(str(count[0][1]) + " has won, with " + str(count[0][0]) + " pieces. " + str(
                count[1][1]) + " lost, with " + str(count[1][0]) + " pieces.")


class SavedGamesLoader(Othello):
    """Loads the board to show previous games."""

    def __init__(self, save_name, seek_amount=64):
        self.save_name = save_name
        self.seek_amount = max(seek_amount, 0)
        self.current_line = 0
        self.commands = None
        self.max_line = 1
        self.previous_states = []
        self.colour = 'W'
        super().__init__([[START_POS.get((x, y), "E") for x in range(BOARD_SIZE)] for y in range(BOARD_SIZE)])

    def load(self):
        """
        This must be run before anything else, will load the file right to the end and
        will load the file into the self.commands array.
        """

        if not self.commands:
            with open(path.join(SAVE_DIR, self.save_name), 'r') as file:
                self.commands = file.readlines()
            self.max_line = len(self.commands)
        line_count = 0
        for line, self.colour in zip(self.commands, self.end_game_iterator(FLIP_RULE[self.colour])):
            self.previous_states.append(deepcopy((self.board, self.colour)))
            if line_count == self.seek_amount:
                break
            line_count += 1
            if not (tup := self.can_be_placed(self.get_pos(line), self.colour))[1]:  # Walrus op for the win
                raise BoardError("Incorrect Board")  # TODO
            self.place(tup[0], self.colour)
        self.previous_states.append(deepcopy((self.board, self.colour)))
        self.current_line = self.max_line
        return ["PrintFull"], self.board

    def line_load_forwards(self):
        """Will load the line forwards."""

        if self.current_line < self.max_line:
            self.current_line += 1
            self.update_board_state(*self.previous_states[self.current_line])
            return LOCAL_IO["Board"], self.board
        else:
            raise BoardError("At end of Board")

    def line_load_backwards(self):
        """Will load the line backwards."""

        if self.current_line > 0:
            self.current_line -= 1
            self.update_board_state(*self.previous_states[self.current_line])
            return LOCAL_IO["Board"], self.board
        else:
            raise BoardError("At start of Board")

    def line_load_current(self):
        """Returns the current board."""

        return LOCAL_IO["Board"], self.board

    def update_board_state(self, board, colour):
        """Updates the board states correctly by calling board_change."""

        self.colour = colour
        self.board = board
        self.board_change()

    @staticmethod
    def get_pos(line):
        """Gets the position from the commands."""

        line = line.split(",")
        return int(line[0]), int(line[1])

    def delete_file(self):
        """Deletes the file."""

        remove(path.join(SAVE_DIR, self.save_name))


def load_othello(games, queue):
    """Used in thread to load all saved games into queue."""

    for game in games:
        loaded = SavedGamesLoader(game)
        try:
            loaded.load()
        except BoardError:
            queue.put((LOCAL_IO["Fail"], loaded))
        except ValueError:
            queue.put((LOCAL_IO["Fail"], loaded))
        else:
            queue.put((LOCAL_IO["Loader"], loaded))
