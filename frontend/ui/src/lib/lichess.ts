// Lichess game URLs come in a few shapes:
//   https://lichess.org/{8charId}
//   https://lichess.org/{12charId}/white
//   https://lichess.org/{12charId}/black
//   http://lichess.org/{id}
// All of them embed via the canonical 8-char id.
export function lichessGameId(gameLink: string): string | null {
  if (!gameLink) return null;
  const match = gameLink.match(/lichess\.org\/([A-Za-z0-9]+)/);
  if (!match || !match[1]) return null;
  return match[1].slice(0, 8);
}

export function lichessEmbedUrl(gameLink: string): string | null {
  const id = lichessGameId(gameLink);
  if (!id) return null;
  return `https://lichess.org/embed/${id}?theme=auto&bg=auto`;
}
