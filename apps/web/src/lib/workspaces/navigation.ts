type WorkspaceCreator = (name: string, description: string | null) => Promise<string>;

export function workspaceNavigation(push: (href: string) => void, createWorkspace: WorkspaceCreator) {
  const open = (id: string) => push(`/workspaces/${encodeURIComponent(id)}`);
  const createAndOpen = async (name: string, description: string | null) => {
    const id = await createWorkspace(name, description);
    open(id);
  };
  return { open, createAndOpen };
}
