"use client";

import { use } from "react";
import EstimateWizard from "../../estimate-wizard";

export default function EstimateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <main className="px-4 py-6 sm:px-6 lg:px-10 lg:py-7">
      <div className="w-full">
        <EstimateWizard initialEstimateSetId={id} />
      </div>
    </main>
  );
}
