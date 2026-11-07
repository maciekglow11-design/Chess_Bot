#!/usr/bin/env python3
"""Play Chess_Bot against a local Stockfish binary and save/review PGN games."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
OUR_ENGINE = [sys.executable, str(ROOT / "engine.py")]


def make_limit(args: argparse.Namespace) -> chess.engine.Limit:
    if args.depth is not None:
        return chess.engine.Limit(depth=args.depth)
    return chess.engine.Limit(time=args.seconds)


def configure_hash(engine: chess.engine.SimpleEngine, size_mb: int) -> None:
    if "Hash" in engine.options:
        engine.configure({"Hash": size_mb})


def our_color_for_game(choice: str, game_number: int) -> chess.Color:
    if choice == "white":
        return chess.WHITE
    if choice == "black":
        return chess.BLACK
    return chess.WHITE if game_number % 2 == 1 else chess.BLACK


def score_cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Convert a score to centipawns, using a large finite value for mate."""
    return score.pov(color).score(mate_score=100_000) or 0


def review_our_moves(stockfish: chess.engine.SimpleEngine, game: chess.pgn.Game,
                     our_color: chess.Color, depth: int) -> list[tuple[int, str, int, str]]:
    """Return (ply, played move, centipawn loss, best move) for our moves."""
    board = game.board()
    mistakes = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        mover = board.turn
        if mover == our_color:
            before = stockfish.analyse(board, chess.engine.Limit(depth=depth))
            best_move = before.get("pv", [None])[0]
            board.push(move)
            after = stockfish.analyse(board, chess.engine.Limit(depth=depth))
            loss = max(0, score_cp(before["score"], mover) - score_cp(after["score"], mover))
            mistakes.append((ply, move.uci(), loss, best_move.uci() if best_move else "?"))
        else:
            board.push(move)
    return mistakes


def play_game(our_engine: chess.engine.SimpleEngine,
              stockfish: chess.engine.SimpleEngine,
              our_color: chess.Color,
              limit: chess.engine.Limit,
              game_number: int,
              max_plies: int) -> chess.pgn.Game:
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess_Bot vs Stockfish"
    game.headers["Site"] = "Local"
    game.headers["Round"] = str(game_number)
    game.headers["White"] = "Chess_Bot" if our_color == chess.WHITE else "Stockfish"
    game.headers["Black"] = "Stockfish" if our_color == chess.WHITE else "Chess_Bot"
    game.headers["TimeControl"] = str(limit.time) if limit.time is not None else f"depth {limit.depth}"
    node = game

    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        is_ours = board.turn == our_color
        player = our_engine if is_ours else stockfish
        result = player.play(board, limit)
        move = result.move
        if move is None or move not in board.legal_moves:
            raise RuntimeError(f"Engine returned an illegal or missing move: {move}")
        san = board.san(move)
        board.push(move)
        node = node.add_variation(move)
        side = "Chess_Bot" if is_ours else "Stockfish"
        print(f"Game {game_number}: {board.fullmove_number - (1 if board.turn == chess.BLACK else 0)}. {side}: {san} ({move.uci()})", flush=True)

    if board.is_game_over(claim_draw=True):
        game.headers["Result"] = board.result(claim_draw=True)
        game.headers["Termination"] = board.outcome(claim_draw=True).termination.name
    else:
        game.headers["Result"] = "1/2-1/2"
        game.headers["Termination"] = f"Move limit ({max_plies} plies)"
    print(f"Game {game_number} result: {game.headers['Result']} ({game.headers['Termination']})")
    print(board, "\n")
    return game


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stockfish", required=True, help="Path to an already installed Stockfish executable")
    parser.add_argument("--games", type=int, default=2, help="Number of games (default: 2)")
    parser.add_argument("--our-color", choices=("white", "black", "alternate"), default="alternate")
    parser.add_argument("--depth", type=int, help="Fixed search depth (overrides --seconds)")
    parser.add_argument("--seconds", type=float, default=1.0, help="Time per move in seconds (default: 1)")
    parser.add_argument("--hash-mb", type=int, default=32, help="Hash option for both engines where supported")
    parser.add_argument("--analysis-depth", type=int, default=10,
                        help="Stockfish depth for post-game move review; set 0 to disable")
    parser.add_argument("--max-plies", type=int, default=300, help="Safety cap on game length")
    parser.add_argument("--output", type=Path, default=Path("stockfish_games.pgn"), help="PGN output path")
    args = parser.parse_args()
    if args.games < 1 or args.hash_mb < 1 or args.max_plies < 1:
        parser.error("--games, --hash-mb and --max-plies must be positive")
    if args.depth is not None and args.depth < 1:
        parser.error("--depth must be positive")
    if args.depth is None and args.seconds <= 0:
        parser.error("--seconds must be positive")
    if args.analysis_depth < 0:
        parser.error("--analysis-depth cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    limit = make_limit(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print("Starting Chess_Bot and local Stockfish; no server or paid service is used.")
    print(f"Chess_Bot command: {OUR_ENGINE}")
    print(f"Stockfish executable: {args.stockfish}")

    with chess.engine.SimpleEngine.popen_uci(OUR_ENGINE) as our_engine, \
            chess.engine.SimpleEngine.popen_uci(args.stockfish) as stockfish:
        configure_hash(our_engine, args.hash_mb)
        configure_hash(stockfish, args.hash_mb)
        with args.output.open("w", encoding="utf-8") as pgn_file:
            for game_number in range(1, args.games + 1):
                our_color = our_color_for_game(args.our_color, game_number)
                game = play_game(our_engine, stockfish, our_color, limit, game_number, args.max_plies)
                if args.analysis_depth:
                    print(f"Stockfish review of Chess_Bot moves (depth {args.analysis_depth}):")
                    mistakes = review_our_moves(stockfish, game, our_color, args.analysis_depth)
                    if not mistakes:
                        print("  No Chess_Bot moves to review.")
                    for ply, played, loss, best in mistakes:
                        label = "BLUNDER" if loss >= 250 else "mistake" if loss >= 100 else "inaccuracy" if loss >= 50 else ""
                        print(f"  ply {ply}: played {played}, best {best}, estimated loss {loss} cp {label}")
                print(chess.pgn.StringExporter(headers=True, variations=True, comments=True).観(game) if False else "")
                exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
                pgn_file.write(game.accept(exporter) + "\n\n")
                pgn_file.flush()
    print(f"Saved PGN games to: {args.output.resolve()}")
    print("Share the PGN and the move/position where Chess_Bot went wrong for targeted fixes.")


if __name__ == "__main__":
    main()
