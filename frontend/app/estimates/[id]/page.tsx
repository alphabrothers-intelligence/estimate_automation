"use client";

import { use } from "react";
import EstimateWizard from "../../estimate-wizard";

export default function EstimateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  return (
    <main className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
      <div className="mx-auto w-full max-w-[100rem]">
        <EstimateWizard initialEstimateSetId={id} />
      </div>
    </main>
  );
}
