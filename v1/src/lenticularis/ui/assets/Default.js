import { d as defineComponent, o as openBlock, c as createBlock, w as withCtx, a as createVNode, V as VMain, r as resolveComponent, b as VApp, D as DefaultBar, e as VFooter } from "./index.js";
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "View",
  setup(__props) {
    return (_ctx, _cache) => {
      const _component_router_view = resolveComponent("router-view");
      return openBlock(), createBlock(VMain, null, {
        default: withCtx(() => [
          createVNode(_component_router_view)
        ]),
        _: 1
      });
    };
  }
});
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Default",
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createBlock(VApp, null, {
        default: withCtx(() => [
          createVNode(DefaultBar),
          createVNode(_sfc_main$1),
          createVNode(VFooter, { class: "bg-grey-lighten-1" })
        ]),
        _: 1
      });
    };
  }
});
export {
  _sfc_main as default
};
