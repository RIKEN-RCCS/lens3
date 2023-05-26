import { d as defineComponent, o as openBlock, c as createBlock, w as withCtx, a as createVNode, V as VMain, r as resolveComponent, _ as _export_sfc, b as VFooter, e as VApp, D as DefaultBar } from "./index.js";
const _sfc_main$2 = /* @__PURE__ */ defineComponent({
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
const _sfc_main$1 = {
  setup() {
    return {};
  }
};
function _sfc_render(_ctx, _cache, $props, $setup, $data, $options) {
  return openBlock(), createBlock(VFooter, { class: "bg-grey-lighten-1" });
}
const DefaultFooter = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["render", _sfc_render]]);
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "Default",
  setup(__props) {
    return (_ctx, _cache) => {
      return openBlock(), createBlock(VApp, null, {
        default: withCtx(() => [
          createVNode(DefaultBar),
          createVNode(_sfc_main$2),
          createVNode(DefaultFooter)
        ]),
        _: 1
      });
    };
  }
});
export {
  _sfc_main as default
};
