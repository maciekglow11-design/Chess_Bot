#!/usr/bin/env python3
"""Experimental UCI chess engine with opening book and tactical search."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import Optional

import chess
import chess.polyglot

from opening_book import choose_book_move

MATE = 30_000
MATE_THRESHOLD = 29_000
INF = 32_000
EXACT, LOWER, UPPER = 0, 1, 2
PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 335,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20_000,
}


def static_exchange_eval(board: chess.Board, move: chess.Move) -> int:
    """Approximate material balance of a capture sequence on move.to_square."""
    if not board.is_capture(move) and not move.promotion:
        return 0

    if board.is_en_passant(move):
        captured_square = move.to_square - 8 if board.turn == chess.WHITE else move.to_square + 8
        victim = board.piece_at(captured_square)
    else:
        victim = board.piece_at(move.to_square)
    gain = [PIECE_VALUE[victim.piece_type] if victim else 0]
    if move.promotion:
        gain[0] += PIECE_VALUE[move.promotion] - PIECE_VALUE[chess.PAWN]

    position = board.copy(stack=False)
    position.push(move)
    target = move.to_square
    occupant = position.piece_at(target)
    if occupant is None:
        return gain[0]
    side = position.turn

    # Repeatedly exchange on the target square using the least valuable attacker.
    # This is intentionally a fast ordering estimate, not full legal SEE.
    for _ in range(30):
        attackers = position.attackers(side, target)
        if not attackers:
            break
        attacker_square = min(
            attackers,
            key=lambda sq: (PIECE_VALUE[position.piece_at(sq).piece_type], sq),
        )
        attacker = position.piece_at(attacker_square)
        gain.append(PIECE_VALUE[occupant.piece_type] - gain[-1])
        position.remove_piece_at(target)
        position.remove_piece_at(attacker_square)
        position.set_piece_at(target, attacker)
        occupant = attacker
        side = not side

    for index in range(len(gain) - 1, 0, -1):
        gain[index - 1] = -max(-gain[index - 1], gain[index])
    return gain[0]


def evaluate(board: chess.Board) -> int:
    """Return a simple side-to-move positional score in centipawns."""
    score = 0
    pawns = {chess.WHITE: [], chess.BLACK: []}
    non_pawn_material = sum(
        PIECE_VALUE[p.piece_type] for p in board.piece_map().values()
        if p.piece_type not in (chess.PAWN, chess.KING)
    )

    for square, piece in board.piece_map().items():
        color = piece.color
        sign = 1 if color == chess.WHITE else -1
        kind = piece.piece_type
        file_index = chess.square_file(square)
        rank_index = chess.square_rank(square)
        relative_rank = rank_index if color == chess.WHITE else 7 - rank_index
        center = 14 - abs(2 * file_index - 7) - abs(2 * rank_index - 7)
        score += sign * PIECE_VALUE[kind]
        if kind == chess.PAWN:
            pawns[color].append(square)
            score += sign * (relative_rank * 7 + center * 2)
        elif kind == chess.KNIGHT:
            score += sign * center * 5
        elif kind == chess.BISHOP:
            score += sign * center * 3
        elif kind == chess.ROOK:
            score += sign * relative_rank * 2
            if relative_rank == 6:
                score += sign * 12
        elif kind == chess.QUEEN:
            score += sign * center
        elif kind == chess.KING:
            score += sign * (center * 4 if non_pawn_material < 2_000 else -center * 3)

    for color in (chess.WHITE, chess.BLACK):
        sign = 1 if color == chess.WHITE else -1
        files = [chess.square_file(sq) for sq in pawns[color]]
        for file_index in range(8):
            count = files.count(file_index)
            if count > 1:
                score -= sign * 12 * (count - 1)
        for square in pawns[color]:
            file_index = chess.square_file(square)
            if not any(abs(other_file - file_index) == 1 for other_file in files):
                score -= sign * 10
            relative_rank = chess.square_rank(square) if color == chess.WHITE else 7 - chess.square_rank(square)
            passed = not any(
                abs(chess.square_file(enemy_sq) - file_index) <= 1
                and (chess.square_rank(enemy_sq) if color == chess.WHITE else 7 - chess.square_rank(enemy_sq)) > relative_rank
                for enemy_sq in pawns[not color]
            )
            if passed:
                score += sign * (10 + relative_rank * relative_rank * 2)
        if len(board.pieces(chess.BISHOP, color)) >= 2:
            score += sign * 28

        king = board.king(color)
        if king is not None and non_pawn_material >= 2_000:
            forward = 1 if color == chess.WHITE else -1
            cover = 0
            for df in (-1, 0, 1):
                file_index = chess.square_file(king) + df
                rank_index = chess.square_rank(king) + forward
                if 0 <= file_index < 8 and 0 <= rank_index < 8:
                    if board.piece_at(chess.square(file_index, rank_index)) == chess.Piece(chess.PAWN, color):
                        cover += 1
            score += sign * (cover * 5 - (3 - cover) * 4)

    return (score if board.turn == chess.WHITE else -score) + 10


def score_to_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score + ply
    if score < -MATE_THRESHOLD:
        return score - ply
    return score


def score_from_tt(score: int, ply: int) -> int:
    if score > MATE_THRESHOLD:
        return score - ply
    if score < -MATE_THRESHOLD:
        return score + ply
    return score


@dataclass
class SearchLimits:
    max_depth: int = 64
    deadline: Optional[float] = None
    max_nodes: Optional[int] = None


class SearchStopped(Exception):
    pass


class Searcher:
    def __init__(self, stop_event: threading.Event, info_callback=None,
                 tt: Optional[dict] = None, max_tt_entries: int = 24_000):
        self.stop_event = stop_event
        self.info_callback = info_callback
        self.nodes = 0
        self.tt = tt if tt is not None else {}
        self.max_tt_entries = max_tt_entries
        self.killers: dict[int, list[chess.Move]] = {}
        self.history: dict[tuple[bool, chess.Move], int] = {}
        self.countermoves: dict[tuple[bool, int, int], chess.Move] = {}
        self.pv: dict[int, list[chess.Move]] = {}
        self.limits = SearchLimits()

    def check_stop(self) -> None:
        if self.stop_event.is_set():
            raise SearchStopped
        if self.limits.deadline is not None and time.monotonic() >= self.limits.deadline:
            raise SearchStopped
        if self.limits.max_nodes is not None and self.nodes >= self.limits.max_nodes:
            raise SearchStopped

    @staticmethod
    def position_key(board: chess.Board) -> tuple[int, int]:
        return chess.polyglot.zobrist_hash(board), min(board.halfmove_clock, 100)

    def terminal_score(self, board: chess.Board, ply: int) -> Optional[int]:
        if board.is_checkmate():
            return -MATE + ply
        if (board.is_stalemate() or board.is_insufficient_material() or
                board.is_fifty_moves() or board.can_claim_threefold_repetition()):
            return 0
        return None

    def move_order_score(self, board: chess.Board, move: chess.Move, ply: int,
                         tt_move: Optional[chess.Move]) -> int:
        if move == tt_move:
            return 2_000_000
        if move.promotion:
            return 1_500_000 + PIECE_VALUE[move.promotion]
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            victim_value = PIECE_VALUE[victim.piece_type] if victim else PIECE_VALUE[chess.PAWN]
            exchange = static_exchange_eval(board, move)
            score = 1_000_000 + exchange * 100 + victim_value
            if board.gives_check(move):
                score += 50_000
            return score
        if board.gives_check(move):
            return 900_000
        killers = self.killers.get(ply, [])
        if move in killers:
            return 800_000 - killers.index(move)
        if len(board.move_stack) >= 1:
            previous = board.peek()
            counter = self.countermoves.get((board.turn, previous.from_square, previous.to_square))
            if move == counter:
                return 750_000
        return self.history.get((board.turn, move), 0)

    def ordered_moves(self, board: chess.Board, ply: int, tt_move=None):
        return sorted(board.legal_moves,
                      key=lambda m: self.move_order_score(board, m, ply, tt_move), reverse=True)

    def quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int, qply: int = 0) -> int:
        self.nodes += 1
        if (self.nodes & 127) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        in_check = board.is_check()
        if qply >= 16:
            if not in_check:
                return evaluate(board)
            evasions = list(board.legal_moves)
            if not evasions:
                return -MATE + ply
            best = -INF
            for move in evasions:
                board.push(move)
                try:
                    value = -evaluate(board)
                finally:
                    board.pop()
                best = max(best, value)
            return best

        if not in_check:
            stand_pat = evaluate(board)
            if stand_pat >= beta:
                return beta
            alpha = max(alpha, stand_pat)
            moves = [m for m in board.legal_moves if m.is_capture() or m.promotion]
        else:
            moves = list(board.legal_moves)

        for move in sorted(moves, key=lambda m: self.move_order_score(board, m, ply, None), reverse=True):
            # Delta/SEE pruning discards clearly losing, non-checking captures in
            # quiet positions. Promotions and checks are always searched.
            if not in_check and not move.promotion and not board.gives_check(move):
                if static_exchange_eval(board, move) < -180:
                    continue
            board.push(move)
            try:
                value = -self.quiescence(board, -beta, -alpha, ply + 1, qply + 1)
            finally:
                board.pop()
            if value >= beta:
                return beta
            alpha = max(alpha, value)
        return alpha

    def _can_null_prune(self, board: chess.Board, depth: int, beta: int) -> bool:
        if depth < 3 or board.is_check() or beta >= MATE_THRESHOLD or board.halfmove_clock >= 90:
            return False
        if board.move_stack and board.peek().is_null():
            return False
        rooks_queens = board.pieces_mask(chess.ROOK, board.turn) | board.pieces_mask(chess.QUEEN, board.turn)
        minors = board.pieces_mask(chess.KNIGHT, board.turn) | board.pieces_mask(chess.BISHOP, board.turn)
        return bool(rooks_queens or chess.popcount(minors) >= 2)

    def _remember_quiet_cutoff(self, board: chess.Board, move: chess.Move, ply: int, depth: int) -> None:
        killers = self.killers.setdefault(ply, [])
        if move not in killers:
            killers.insert(0, move)
            del killers[2:]
        history_key = (board.turn, move)
        self.history[history_key] = min(100_000, self.history.get(history_key, 0) + depth * depth)
        if len(board.move_stack) >= 1:
            previous = board.peek()
            self.countermoves[(board.turn, previous.from_square, previous.to_square)] = move

    def negamax(self, board: chess.Board, depth: int, alpha: int, beta: int, ply: int) -> int:
        self.nodes += 1
        if (self.nodes & 127) == 0:
            self.check_stop()
        terminal = self.terminal_score(board, ply)
        if terminal is not None:
            return terminal
        if depth <= 0:
            return self.quiescence(board, alpha, beta, ply)
        if board.is_check():
            depth += 1

        original_alpha = alpha
        key = self.position_key(board)
        entry = self.tt.get(key)
        tt_move = None
        if entry:
            tt_depth, tt_score, flag, tt_move = entry
            tt_score = score_from_tt(tt_score, ply)
            if tt_depth >= depth:
                if flag == EXACT or (flag == LOWER and tt_score >= beta) or (flag == UPPER and tt_score <= alpha):
                    return tt_score

        if self._can_null_prune(board, depth, beta):
            reduction = 2 + depth // 6
            board.push(chess.Move.null())
            try:
                null_score = -self.negamax(board, depth - 1 - reduction, -beta, -beta + 1, ply + 1)
            finally:
                board.pop()
            if null_score >= beta:
                return null_score

        best_score = -INF
        best_move = None
        moves = self.ordered_moves(board, ply, tt_move)
        for index, move in enumerate(moves):
            quiet = not board.is_capture(move) and not move.promotion
            gives_check = board.gives_check(move)
            board.push(move)
            try:
                if index == 0:
                    value = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
                else:
                    reduction = 1 if depth >= 3 and index >= 3 and quiet and not gives_check else 0
                    value = -self.negamax(board, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1)
                    if value > alpha and reduction:
                        value = -self.negamax(board, depth - 1, -alpha - 1, -alpha, ply + 1)
                    if alpha < value < beta:
                        value = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            finally:
                board.pop()

            if value > best_score:
                best_score = value
                best_move = move
                self.pv[ply] = [move] + self.pv.get(ply + 1, [])
            alpha = max(alpha, value)
            if alpha >= beta:
                if quiet:
                    self._remember_quiet_cutoff(board, move, ply, depth)
                break

        if best_move is None:
            return 0
        flag = UPPER if best_score <= original_alpha else LOWER if best_score >= beta else EXACT
        if len(self.tt) >= self.max_tt_entries:
            self.tt.clear()
        old = self.tt.get(key)
        if old is None or depth >= old[0] or flag == EXACT:
            self.tt[key] = (depth, score_to_tt(best_score, ply), flag, best_move)
        return best_score

    def search_root(self, board: chess.Board, depth: int, alpha: int, beta: int):
        original_alpha = alpha
        best_score = -INF
        best_move = next(iter(board.legal_moves))
        key = self.position_key(board)
        entry = self.tt.get(key)
        moves = self.ordered_moves(board, 0, entry[3] if entry else None)
        for index, move in enumerate(moves):
            self.check_stop()
            board.push(move)
            try:
                if index == 0:
                    value = -self.negamax(board, depth - 1, -beta, -alpha, 1)
                else:
                    value = -self.negamax(board, depth - 1, -alpha - 1, -alpha, 1)
                    if alpha < value < beta:
                        value = -self.negamax(board, depth - 1, -beta, -alpha, 1)
            finally:
                board.pop()
            if value > best_score:
                best_score, best_move = value, move
                self.pv[0] = [move] + self.pv.get(1, [])
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        flag = UPPER if best_score <= original_alpha else LOWER if best_score >= beta else EXACT
        self.tt[key] = (depth, score_to_tt(best_score, 0), flag, best_move)
        return best_score, best_move, self.pv.get(0, [best_move])

    def run(self, board: chess.Board, limits: SearchLimits) -> chess.Move:
        self.limits = limits
        legal_moves = list(board.legal_moves)
        if not legal_moves:
            return chess.Move.null()
        best_move = legal_moves[0]
        previous_score = 0
        started = time.monotonic()
        for depth in range(1, limits.max_depth + 1):
            window = 50 if depth > 1 else INF
            alpha, beta = max(-INF, previous_score - window), min(INF, previous_score + window)
            try:
                while True:
                    self.pv.clear()
                    score, candidate, pv = self.search_root(board, depth, alpha, beta)
                    if score <= alpha and alpha > -INF:
                        window *= 2
                        alpha = max(-INF, previous_score - window)
                        continue
                    if score >= beta and beta < INF:
                        window *= 2
                        beta = min(INF, previous_score + window)
                        continue
                    break
            except SearchStopped:
                break
            best_move, previous_score = candidate, score
            elapsed_ms = max(1, int((time.monotonic() - started) * 1000))
            if self.info_callback:
                self.info_callback(depth, score, self.nodes, elapsed_ms, pv)
            if abs(score) >= MATE - depth:
                break
        return best_move


_output_lock = threading.Lock()
_state_lock = threading.Lock()
_board = chess.Board()
_worker: Optional[threading.Thread] = None
_stop_event: Optional[threading.Event] = None
_hash_mb = 16
_move_overhead_ms = 30
_use_book = True
_tt: dict = {}


def send(line: str) -> None:
    with _output_lock:
        print(line, flush=True)


def parse_go(tokens: list[str], board: Optional[chess.Board] = None) -> SearchLimits:
    values: dict[str, int] = {}
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token in {"infinite", "ponder"}:
            values[token] = 1
            i += 1
        elif token in {"wtime", "btime", "winc", "binc", "movestogo", "depth", "nodes", "movetime"} and i + 1 < len(tokens):
            try:
                values[token] = int(tokens[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    max_depth = max(1, min(values.get("depth", 64), 64))
    max_nodes = max(1, values["nodes"]) if "nodes" in values else None
    deadline = None
    if "movetime" in values:
        deadline = time.monotonic() + max(0.001, (values["movetime"] - _move_overhead_ms) / 1000)
    elif "infinite" not in values and ("wtime" in values or "btime" in values):
        turn = board.turn if board is not None else _board.turn
        remaining = max(1, values.get("wtime" if turn == chess.WHITE else "btime", 1_000))
        increment = max(0, values.get("winc" if turn == chess.WHITE else "binc", 0))
        usable = max(1, remaining - _move_overhead_ms)
        allocation = max(1, min(usable * 0.7, usable / max(1, values.get("movestogo", 30)) + increment * 0.8))
        deadline = time.monotonic() + allocation / 1000
    return SearchLimits(max_depth, deadline, max_nodes)


def stop_search() -> None:
    global _worker, _stop_event
    worker, event = _worker, _stop_event
    if event:
        event.set()
    if worker and worker.is_alive() and worker is not threading.current_thread():
        worker.join()
    _worker = None
    _stop_event = None


def start_search(tokens: list[str]) -> None:
    global _worker, _stop_event
    stop_search()
    with _state_lock:
        board = _board.copy(stack=True)
    if _use_book:
        book_move = choose_book_move(board)
        if book_move is not None:
            send(f"info string opening book move {book_move.uci()}")
            send(f"bestmove {book_move.uci()}")
            return
    limits = parse_go(tokens, board)
    event = threading.Event()
    _stop_event = event

    def report(depth, score, nodes, elapsed_ms, pv):
        if abs(score) >= MATE_THRESHOLD:
            mate = max(1, (MATE - abs(score) + 1) // 2)
            score_text = f"mate {mate if score > 0 else -mate}"
        else:
            score_text = f"cp {score}"
        pv_text = " ".join(move.uci() for move in pv)
        send(f"info depth {depth} score {score_text} nodes {nodes} nps {nodes * 1000 // max(1, elapsed_ms)} time {elapsed_ms} pv {pv_text}".rstrip())

    def work():
        searcher = Searcher(event, report, _tt, max(1_000, _hash_mb * 1_500))
        best = searcher.run(board, limits)
        send(f"bestmove {best.uci()}")

    _worker = threading.Thread(target=work, daemon=True)
    _worker.start()


def set_position(tokens: list[str]) -> None:
    global _board
    try:
        if len(tokens) < 2:
            return
        if tokens[1] == "startpos":
            board, index = chess.Board(), 2
        elif tokens[1] == "fen" and len(tokens) >= 8:
            board, index = chess.Board(" ".join(tokens[2:8])), 8
        else:
            raise ValueError("expected startpos or fen")
        if index < len(tokens) and tokens[index] == "moves":
            for uci in tokens[index + 1:]:
                board.push_uci(uci)
        with _state_lock:
            _board = board
    except (ValueError, IndexError) as exc:
        send(f"info string Invalid position command: {exc}")


def set_option(tokens: list[str]) -> None:
    global _hash_mb, _move_overhead_ms, _use_book
    try:
        name_index = tokens.index("name") + 1
        value_index = tokens.index("value")
        name = " ".join(tokens[name_index:value_index]).lower()
        value = tokens[value_index + 1]
        if name == "hash":
            _hash_mb = max(1, min(int(value), 256))
            _tt.clear()
        elif name == "move overhead":
            _move_overhead_ms = max(0, min(int(value), 5_000))
        elif name == "use book":
            _use_book = value.lower() in {"true", "1", "on", "yes"}
    except (ValueError, IndexError):
        return


def main() -> None:
    for raw_line in sys.stdin:
        tokens = raw_line.strip().split()
        if not tokens:
            continue
        command = tokens[0]
        if command == "uci":
            send("id name Chess_Bot Python")
            send("id author maciekglow11-design")
            send("option name Hash type spin default 16 min 1 max 256")
            send("option name Move Overhead type spin default 30 min 0 max 5000")
            send("option name Use Book type check default true")
            send("uciok")
        elif command == "isready":
            send("readyok")
        elif command == "ucinewgame":
            stop_search()
            _tt.clear()
        elif command == "position":
            stop_search()
            set_position(tokens)
        elif command == "go":
            start_search(tokens)
        elif command == "stop":
            stop_search()
        elif command == "setoption":
            set_option(tokens)
        elif command == "quit":
            stop_search()
            break


if __name__ == "__main__":
    main()
