import type {
  BuyRequest,
  Credits,
  DemoActor,
  Events,
  Health,
  History,
  IssueRequest,
  Job,
  JobAccepted,
  Operation,
  OperationAccepted,
  Plot,
  Plots,
  Proof,
  TransferRequest,
  Verification,
  VerificationEvidence,
  VerifyRequest,
} from './types';

export type AdapterKind = 'http' | 'fixture';

export interface RequestOptions {
  signal?: AbortSignal;
}

export interface MutationOptions extends RequestOptions {
  idempotencyKey: string;
}

export type ArtifactPayload =
  | { kind: 'image'; src: string; mediaType: string; release: () => void }
  | { kind: 'geojson'; data: GeoJSON.GeoJsonObject; mediaType: string; release: () => void };

export interface EventsQuery {
  plotId: string;
  cursor?: string;
  limit?: number;
}

// Maps 1:1 to contracts/openapi.yaml operations; both adapters implement exactly this.
export interface MrvApiClient {
  readonly kind: AdapterKind;
  getHealth(opts?: RequestOptions): Promise<Health>;
  listPlots(opts?: RequestOptions): Promise<Plots>;
  getPlot(plotId: string, actor: DemoActor, opts?: RequestOptions): Promise<Plot>;
  startVerification(plotId: string, actor: DemoActor, body: VerifyRequest, opts: MutationOptions): Promise<JobAccepted>;
  getJob(statusUrlOrId: string, opts?: RequestOptions): Promise<Job>;
  getVerification(verificationId: string, opts?: RequestOptions): Promise<Verification>;
  getProof(verificationId: string, opts?: RequestOptions): Promise<Proof>;
  getCanonicalEvidence(verificationId: string, opts?: RequestOptions): Promise<VerificationEvidence>;
  getHistory(plotId: string, opts?: RequestOptions): Promise<History>;
  getCredits(plotId: string, actor: DemoActor, opts?: RequestOptions): Promise<Credits>;
  issueBatch(plotId: string, actor: DemoActor, body: IssueRequest, opts: MutationOptions): Promise<OperationAccepted>;
  buyCredits(batchId: string, actor: DemoActor, body: BuyRequest, opts: MutationOptions): Promise<OperationAccepted>;
  transferCredits(batchId: string, actor: DemoActor, body: TransferRequest, opts: MutationOptions): Promise<OperationAccepted>;
  getOperation(statusUrlOrId: string, opts?: RequestOptions): Promise<Operation>;
  listEvents(query: EventsQuery, opts?: RequestOptions): Promise<Events>;
  getArtifact(artifactUrl: string, mediaType: string, opts?: RequestOptions): Promise<ArtifactPayload>;
}
