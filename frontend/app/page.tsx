import EstimateWizard from "./estimate-wizard";

export default function Home() {
  return (
    <main className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
      <div className="mx-auto w-full max-w-7xl">
        <div className="mb-7">
          <p className="text-sm font-semibold text-indigo-600">견적서 작성</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight text-slate-900">새 견적서 만들기</h1>
          <p className="mt-2 text-sm text-slate-500">과업과 법인을 선택하면 항목과 금액을 자동으로 구성해 드립니다.</p>
        </div>
        <EstimateWizard />
      </div>
    </main>
  );
}
