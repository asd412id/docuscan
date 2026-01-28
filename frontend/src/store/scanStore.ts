import { create } from 'zustand';
import type { Document, CornerPoints, ScanSettings } from '@/types';

// Per-document settings stored by uuid
interface DocumentSettings {
  corners?: CornerPoints;
  settings?: ScanSettings;
}

interface ScanState {
  documents: Document[];
  currentDocument: Document | null;
  corners: CornerPoints | null;
  settings: ScanSettings;  // Default/global settings
  documentSettings: Record<string, DocumentSettings>;  // Per-document overrides
  isProcessing: boolean;
  
  setDocuments: (documents: Document[]) => void;
  addDocument: (document: Document) => void;
  addDocuments: (documents: Document[]) => void;
  removeDocument: (uuid: string) => void;
  reorderDocuments: (fromIndex: number, toIndex: number) => void;
  setCurrentDocument: (document: Document | null) => void;
  updateDocument: (uuid: string, updates: Partial<Document>) => void;
  setCorners: (corners: CornerPoints | null) => void;
  setSettings: (settings: Partial<ScanSettings>) => void;
  setDocumentCorners: (uuid: string, corners: CornerPoints) => void;
  setDocumentSettings: (uuid: string, settings: Partial<ScanSettings>) => void;
  getDocumentSettings: (uuid: string) => { corners?: CornerPoints; settings: ScanSettings };
  setIsProcessing: (isProcessing: boolean) => void;
  resetScan: () => void;
}

const defaultSettings: ScanSettings = {
  filter_mode: 'scan',
  brightness: 0,
  contrast: 0,
  rotation: 0,
  auto_enhance: true,
};

export const useScanStore = create<ScanState>((set, get) => ({
  documents: [],
  currentDocument: null,
  corners: null,
  settings: defaultSettings,
  documentSettings: {},
  isProcessing: false,
  
  setDocuments: (documents) => set({ documents }),
  
  addDocument: (document) => 
    set((state) => ({ documents: [...state.documents, document] })),
  
  addDocuments: (documents) => 
    set((state) => ({ documents: [...state.documents, ...documents] })),
  
  removeDocument: (uuid) =>
    set((state) => {
      const newDocuments = state.documents.filter((d) => d.uuid !== uuid);

      let newCurrent = state.currentDocument;
      if (state.currentDocument?.uuid === uuid) {
        const removedIndex = state.documents.findIndex((d) => d.uuid === uuid);
        const newIndex = Math.min(Math.max(0, removedIndex), newDocuments.length - 1);
        newCurrent = newDocuments[newIndex] ?? null;
      }

      const remainingSettings = Object.fromEntries(
        Object.entries(state.documentSettings).filter(([key]) => key !== uuid)
      );

      return {
        documents: newDocuments,
        currentDocument: newCurrent,
        documentSettings: remainingSettings,
      };
    }),
  
  reorderDocuments: (fromIndex, toIndex) =>
    set((state) => {
      const newDocuments = [...state.documents];
      const [movedDoc] = newDocuments.splice(fromIndex, 1);
      newDocuments.splice(toIndex, 0, movedDoc);
      return { documents: newDocuments };
    }),
  
  setCurrentDocument: (document) => {
    const state = get();
    if (document) {
      const docSettings = state.documentSettings[document.uuid];
      set({ 
        currentDocument: document, 
        corners: docSettings?.corners || null,
      });
    } else {
      set({ currentDocument: null, corners: null });
    }
  },
  
  updateDocument: (uuid, updates) =>
    set((state) => ({
      documents: state.documents.map((d) => 
        d.uuid === uuid ? { ...d, ...updates } : d
      ),
      currentDocument: state.currentDocument?.uuid === uuid 
        ? { ...state.currentDocument, ...updates } 
        : state.currentDocument,
    })),
  
  setCorners: (corners) => {
    const state = get();
    set({ corners });
    // Also save to document-specific settings
    if (state.currentDocument && corners) {
      set((s) => ({
        documentSettings: {
          ...s.documentSettings,
          [state.currentDocument!.uuid]: {
            ...s.documentSettings[state.currentDocument!.uuid],
            corners,
          },
        },
      }));
    }
  },
  
  setSettings: (settings) => 
    set((state) => ({ settings: { ...state.settings, ...settings } })),
  
  setDocumentCorners: (uuid, corners) =>
    set((state) => ({
      documentSettings: {
        ...state.documentSettings,
        [uuid]: { ...state.documentSettings[uuid], corners },
      },
    })),
  
  setDocumentSettings: (uuid, settings) =>
    set((state) => ({
      documentSettings: {
        ...state.documentSettings,
        [uuid]: { 
          ...state.documentSettings[uuid], 
          settings: { ...defaultSettings, ...state.documentSettings[uuid]?.settings, ...settings },
        },
      },
    })),
  
  getDocumentSettings: (uuid) => {
    const state = get();
    const docSettings = state.documentSettings[uuid];
    return {
      corners: docSettings?.corners,
      settings: docSettings?.settings || state.settings,
    };
  },
  
  setIsProcessing: (isProcessing) => set({ isProcessing }),
  
  resetScan: () => set({ 
    documents: [], 
    currentDocument: null, 
    corners: null, 
    settings: defaultSettings,
    documentSettings: {},
    isProcessing: false,
  }),
}));
