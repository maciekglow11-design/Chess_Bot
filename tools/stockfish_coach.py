#!/usr/bin/env python3
"""Play Chess_Bot repeatedly against Stockfish and review its moves.

Stockfish is only an opponent and post-game reviewer. Its suggested moves are
recorded as explanations; this script never feeds them into Chess_Bot during a
game or changes the engine's source code. Ctrl+C stops after the current game.
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

ROOT = Path(__file__).resolve().parents[1]
OUR_ENGINE = [sys.executable, str(ROOT / "engine.py")]


def score_cp(score: chess.engine.PovScore, color: chess.Color) -> int:
    """Convert a score to centipawns from the requested side's perspective."""
    value = score.pov(color).score(mate_score=100_000)
    return 0 if value is None else value


def our_color_for_game(choice: str, game_number: int) -> chess.Color:
    if choice == "white":
        return chess.WHITE
    if choice == "black":
        return chess.BLACK
    return chess.WHITE if game_number % 2 else chess.BLACK


def bot_result_score(result: str, color: chess.Color) -> float:
    """Return 1 for a bot win, 0.5 for draw, and 0 for loss/unknown."""
    if result == "1/2-1/2":
        return 0.5
    return float(result == ("1-0" if color == chess.WHITE else "0-1"))


def review_our_moves(stockfish: chess.engine.SimpleEngine,
                     game: chess.pgn.Game,
                     our_color: chess.Color,
                     depth: int) -> list[tuple[int, str, int, str]]:
    """Return (ply, played UCI, approximate loss cp, best UCI) for bot moves."""
    board = game.board()
    node = game
    mistakes: list[tuple[int, str, int, str]] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if board.turn != our_color:
            board.push(move)
            node = node.variation(move)
            continue

        before = stockfish.analyse(board, chess.engine.Limit(depth=depth), game=game)
        best_move = before.get("pv", [None])[0]
        before_score = score_cp(before["score"], our_color)
        san = board.san(move)
        board.push(move)
        after = stockfish.analyse(board, chess.engine.Limit(depth=depth), game=game)
        after_score = score_cp(after["score"], our_color)
        loss = max(0, before_score - after_score)
        best_text = best_move.uci() if best_move is not None else "?"
        label = "BLUNDER" if loss >= 250 else "mistake" if loss >= 100 else "inaccuracy" if loss >= 50 else ""

        node = node.variation(move)
        node.comment = (f"Stockfish review (depth {depth}): played {san} ({move.uci()}); "
                        f"best {best_text}; approximate loss {loss} cp" +
                        (f" — {label}" if label else ""))
        mistakes.append((ply, move.uci(), loss, best_text))
    return mistakes


def play_game(our_engine: chess.engine.SimpleEngine,
              stockfish: chess.engine.SimpleEngine,
              our_color: chess.Color,
              limit: chess.engine.Limit,
              game_number: int,
              max_plies: int) -> chess.pgn.Game:
    board = chess.Board()
    game = chess.pgn.Game()
    game.headers["Event"] = "Chess_Bot vs Stockfish training"
    game.headers["Site"] = "Local coach"
    game.headers["Round"] = str(game_number)
    game.headers["White"] = "Chess_Bot" if our_color == chess.WHITE else "Stockfish"
    game.headers["Black"] = "Stockfish" if our_color == chess.WHITE else "Chess_Bot"
    game.headers["TimeControl"] = str(limit.time) if limit.time is not None else f"depth {limit.depth}"
    node = game

    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        is_ours = board.turn == our_color
        player = our_engine if is_ours else stockfish
        player_name = "Chess_Bot" if is_ours else "Stockfish"
        result = player.play(board, limit, game=game)
        move = result.move
        if move is None or move not in board.legal_moves:
            raise RuntimeError(f"{player_name} returned an illegal or missing move: {move}")
        san = board.san(move)
        print(f"Game {game_number}: {player_name}: {san} ({move.uci()})", flush=True)
        board.push(move)
        node = node.add_variation(move)

    if board.is_game_over(claim_draw=True):
        game.headers["Result"] = board.result(claim_draw=True)
        outcome = board.outcome(claim_draw=True)
        game.headers["Termination"] = outcome.termination.name if outcome else "Game over"
    else:
        game.headers["Result"] = "1/2-1/2"
        game.headers["Termination"] = f"Move limit ({max_plies} plies)"
    return game


def persist_best_games(best_games: list[dict[str, Any]], output_dir: Path) -> None:
    """Rewrite only this tool's own PGNs; leave unrelated user files untouched."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_path in output_dir.glob("best_*.pgn"):
        old_path.unlink()
    exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
    for index, entry in enumerate(sorted(best_games, key=lambda item: item["total_loss"]), start=1):
        path = output_dir / f"best_{index:02d}_{entry['total_loss']}cp.pgn"
        path.write_text(entry["game"].accept(exporter) + "\n", encoding="utf-8")


def keep_best_games(best_games: list[dict[str, Any]], game: chess.pgn.Game,
                    total_loss: int, keep_best: int,
                    color: chess.Color = chess.WHITE,
                    minimum_result_score: float = 0.5) -> list[dict[str, Any]]:
    """Keep successful games with the lowest analysis loss, up to keep_best."""
    if keep_best < 1:
        return best_games
    if bot_result_score(game.headers.get("Result", "*"), color) < minimum_result_score:
        return best_games
    best_games.append({"game": game, "total_loss": total_loss})
    return sorted(best_games, key=lambda item: item["total_loss"])[:keep_best]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stockfish", required=True, help="Path to an installed Stockfish executable")
    parser.add_argument("--games", type=int, default=0, help="Games to play; 0 means run until Ctrl+C")
    parser.add_argument("--our-color", choices=("white", "black", "alternate"), default="alternate")
    parser.add_argument("--seconds", type=float, default=1.5, help="Time per move in seconds")
    parser.add_argument("--analysis-depth", type=int, default=12, help="Stockfish post-game review depth")
    parser.add_argument("--hash-mb", type=int, default=32, help="Hash size for each engine if supported")
    parser.add_argument("--max-plies", type=int, default=300, help="Safety cap for one game")
    parser.add_argument("--keep-best", type=int, default=10, help="Maximum number of successful games to keep")
    parser.add_argument("--min-result-score", type=float, choices=(0.0, 0.5, 1.0), default=0.5,
                        help="Minimum bot result score to keep: loss=0, draw=0.5, win=1")
    parser.add_argument("--output-dir", type=Path, default=Path("stockfish_coach_games"), help="PGN output directory")
    args = parser.parse_args()
    if args.games < 0 or args.hash_mb < 1 or args.max_plies < 1 or args.keep_best < 1:
        parser.error("--games must be non-negative; --hash-mb, --max-plies, and --keep-best must be positive")
    if args.seconds <= 0 or args.analysis_depth < 1:
        parser.error("--seconds and --analysis-depth must be positive")
    return args


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    best_games: list[dict[str, Any]] = []
    total = 0
    wins = draws = losses = 0
    stop_requested = False

    def handle_signal(signum: int, frame: Any) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"\nStopping after the current game (signal {signum}).", flush=True)

    signal.signal(signal.SIGINT, handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_signal)

    limit = chess.engine.Limit(time=args.seconds)
    print("Stockfish is only the opponent/reviewer; it does not control Chess_Bot's moves.")
    print(f"Best games will be saved in: {args.output_dir.resolve()}")
    try:
        with chess.engine.SimpleEngine.popen_uci(OUR_ENGINE) as our_engine, \
                chess.engine.SimpleEngine.popen_uci(args.stockfish) as stockfish:
            for engine in (our_engine, stockfish):
                if "Hash" in engine.options:
                    engine.configure({"Hash": args.hash_mb})

            while not stop_requested and (args.games == 0 or total < args.games):
                game_number = total + 1
                color = our_color_for_game(args.our_color, game_number)
                game = play_game(our_engine, stockfish, color, limit, game_number, args.max_plies)
                # Count the game as soon as play finishes. This is important for
                # --games: without it the loop repeatedly starts game 1 forever.
                total += 1
                review = review_our_moves(stockfish, game, color, args.analysis_depth)
                total_loss = sum(row[2] for row in review)
                max_loss = max((row[2] for row in review), default=0)
                points = bot_result_score(game.headers["Result"], color)
                wins += int(points == 1.0)
                draws += int(points == 0.5)
                losses += int(points == 0.0)
                best_games = keep_best_games(best_games, game, total_loss, args.keep_best,
                                             color, args.min_result_score)
                persist_best_games(best_games, args.output_dir)
                print(f"Result {game_number}: {game.headers['Result']}; total loss ~{total_loss} cp, "
                      f"worst move ~{max_loss} cp. Record {wins}-{draws}-{losses}; "
                      f"saved {len(best_games)} game(s).", flush=True)
    except KeyboardInterrupt:
        print("\nInterrupted; completed-game data is preserved.", flush=True)
    finally:
        print(f"Finished: {total} completed game(s); {wins} wins, {draws} draws, {losses} losses. "
              f"PGNs: {args.output_dir.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
