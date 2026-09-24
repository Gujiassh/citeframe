type ListTicket = { workspaceId: string; revision: number; sequence: number };

export class AssetListOrder {
  private revisions = new Map<string, number>();
  private applied = new Map<string, number>();
  private sequence = 0;

  begin(workspaceId: string): ListTicket {
    return { workspaceId, revision: this.revisions.get(workspaceId) ?? 0, sequence: ++this.sequence };
  }

  invalidate(workspaceId: string) {
    this.revisions.set(workspaceId, (this.revisions.get(workspaceId) ?? 0) + 1);
  }

  accept(ticket: ListTicket): boolean {
    if (ticket.revision !== (this.revisions.get(ticket.workspaceId) ?? 0)
      || ticket.sequence < (this.applied.get(ticket.workspaceId) ?? 0)) return false;
    this.applied.set(ticket.workspaceId, ticket.sequence);
    return true;
  }
}
