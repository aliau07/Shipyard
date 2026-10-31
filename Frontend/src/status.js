export const STATUS_META = {
  draft: { label: 'Draft', group: 'waiting', icon: 'pencil' },
  in_review: { label: 'In review', group: 'action', icon: 'search-check' },
  approved: { label: 'Approved', group: 'arranged', icon: 'badge-check' },
  in_progress: { label: 'In progress', group: 'arranged', icon: 'circle-play' },
  released: { label: 'Released', group: 'done', icon: 'circle-check' },
  blocked: { label: 'Blocked', group: 'blocked', icon: 'ban' },
  cancelled: { label: 'Cancelled', group: 'neutral', icon: 'circle-slash' },
};

export const STATUS_ORDER = ['draft', 'in_review', 'approved', 'in_progress', 'released', 'blocked', 'cancelled'];
