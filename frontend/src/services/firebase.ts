import { initializeApp } from "firebase/app";
import {
  getFirestore,
  collection,
  addDoc,
  query,
  where,
  getDocs,
  updateDoc,
  deleteDoc,
  doc,
} from "firebase/firestore";
import { getAnalytics } from "firebase/analytics";
import { getAuth, signInAnonymously } from "firebase/auth";

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyAefYNfP4i7lFX7XuZ_pD_4Bpr0RbOTx6c",
  authDomain: "thora-cf789.firebaseapp.com",
  projectId: "thora-cf789",
  storageBucket: "thora-cf789.firebasestorage.app",
  messagingSenderId: "365630687753",
  appId: "1:365630687753:web:7e7e665e6755e2b5acc6d8",
  measurementId: "G-CPHGFSB3V6",
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const analytics = getAnalytics(app);

// Firebase Auth (protects backend endpoints)
const auth = getAuth(app);
let authInitPromise: Promise<string> | null = null;
let firebaseAuthDisabled = false;

export const ensureAuthToken = async (): Promise<string> => {
  if (firebaseAuthDisabled) return "";
  if (authInitPromise) return authInitPromise;

  authInitPromise = (async () => {
    if (auth.currentUser) {
      return auth.currentUser.getIdToken();
    }

    // If anonymous auth is enabled in Firebase, this produces an ID token.
    const result = await signInAnonymously(auth);
    return result.user.getIdToken();
  })();

  try {
    return await authInitPromise;
  } catch (e) {
    // Avoid retry storm when anonymous auth is not configured in Firebase project.
    firebaseAuthDisabled = true;
    authInitPromise = Promise.resolve("");
    return "";
  }
};

// ==================== INTERFACES ====================

export interface ExtractedItem {
  id: string;
  description: string;
  quantity: number;
  unit: string;
  unitValue: number;
  totalValue: number;
}

export interface OrcamentoRecord {
  id?: string;
  uploadId: string;
  filename: string;
  uploadedAt: Date;
  extractedAt?: Date;
  items: ExtractedItem[];
  tablesFound: number;
  status: "processing" | "completed" | "error";
  errorMessage?: string;
}

// ==================== FIRESTORE OPERATIONS ====================

/**
 * Salvar orçamento extraído do PDF
 */
export const saveOrcamento = async (data: OrcamentoRecord) => {
  try {
    const docRef = await addDoc(collection(db, "orcamentos"), {
      uploadId: data.uploadId,
      filename: data.filename,
      uploadedAt: data.uploadedAt,
      extractedAt: new Date(),
      items: data.items,
      tablesFound: data.tablesFound,
      status: data.status || "completed",
      errorMessage: data.errorMessage || null,
    });
    console.log("✅ Orçamento salvo:", docRef.id);
    return docRef.id;
  } catch (error) {
    console.error("❌ Erro ao salvar orçamento:", error);
    throw error;
  }
};

/**
 * Buscar orçamentos por uploadId
 */
export const getOrcamentoByUploadId = async (uploadId: string) => {
  try {
    const q = query(
      collection(db, "orcamentos"),
      where("uploadId", "==", uploadId),
    );
    const querySnapshot = await getDocs(q);

    if (querySnapshot.empty) {
      return null;
    }

    const doc = querySnapshot.docs[0];
    return {
      id: doc.id,
      ...doc.data(),
    } as OrcamentoRecord & { id: string };
  } catch (error) {
    console.error("❌ Erro ao buscar orçamento:", error);
    throw error;
  }
};

/**
 * Listar todos os orçamentos
 */
export const getAllOrcamentos = async () => {
  try {
    const querySnapshot = await getDocs(collection(db, "orcamentos"));
    return querySnapshot.docs.map((doc) => ({
      id: doc.id,
      ...doc.data(),
    })) as (OrcamentoRecord & { id: string })[];
  } catch (error) {
    console.error("❌ Erro ao listar orçamentos:", error);
    throw error;
  }
};

/**
 * Atualizar orçamento
 */
export const updateOrcamento = async (
  documentId: string,
  data: Partial<OrcamentoRecord>,
) => {
  try {
    await updateDoc(doc(db, "orcamentos", documentId), {
      ...data,
      updatedAt: new Date(),
    });
    console.log("✅ Orçamento atualizado:", documentId);
  } catch (error) {
    console.error("❌ Erro ao atualizar orçamento:", error);
    throw error;
  }
};

/**
 * Deletar orçamento
 */
export const deleteOrcamento = async (documentId: string) => {
  try {
    await deleteDoc(doc(db, "orcamentos", documentId));
    console.log("✅ Orçamento deletado:", documentId);
  } catch (error) {
    console.error("❌ Erro ao deletar orçamento:", error);
    throw error;
  }
};

export { db, app, auth };
